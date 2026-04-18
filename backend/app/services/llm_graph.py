from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field

from app.config import settings
from app.core.types import EdgeType, EvidenceChunk, RelationType
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.services.text_utils import canonicalize_term, is_reasonable_term, normalize_text

GRAPH_SYSTEM_PROMPT = """\
你是课程知识图谱抽取器。你的任务是把课堂 slides / notes / transcript 的文本片段清洗为结构化知识点图候选。

只保留真正可教学的概念、术语、定义、方法、结构、规则、约束、模型、操作，不要保留：
- 页眉页脚
- 目录残片
- 章节号
- 示例数据
- 人名、学号、课程号
- 只在例子里有意义的实体

关系限制：
- RELATES_TO 只能用于明确语义关系
- relation_type 只能是 is_a / part_of / prerequisite_of / causes / used_for / similar_to
- CO_OCCURS_WITH 仅表示高频共现，不表示明确语义

输出必须是 JSON object，且只能引用输入里出现过的 chunk_id。
"""

VISION_SYSTEM_PROMPT = """\
你是课堂 PDF 页面文本恢复器。请从页面图片中提取可读文字，尽量保留标题、项目符号、公式附近的自然语言说明和顺序。
不要解释图片，不要总结，不要输出 JSON，只返回提取出的纯文本。
如果页面几乎不可读或没有文字，返回空字符串。
"""

NOISE_PATTERNS = [
    re.compile(r"^\d+(\.\d+)+$"),
    re.compile(r"^(chapter|section|lecture|slide)\b", re.IGNORECASE),
]
NOISE_SUBSTRINGS = {
    "本章",
    "目录",
    "contents",
    "outline",
    "example",
    "student",
    "学号",
    "课程号",
    "姓名",
    "page",
}
VALID_RELATION_TYPES = {item.value for item in RelationType}


class ExtractedConcept(BaseModel):
    name: str
    canonical_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class ExtractedRelation(BaseModel):
    source_canonical_name: str
    target_canonical_name: str
    edge_type: str = EdgeType.relates_to.value
    relation_type: str | None = None
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.72


class GraphExtractionResult(BaseModel):
    concepts: list[ExtractedConcept] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


def llm_graph_configured() -> bool:
    return bool(settings.graph_llm_api_key and settings.graph_llm_model)


def pdf_visual_fallback_configured() -> bool:
    return bool(settings.pdf_vision_api_key and settings.pdf_vision_model)


def extract_graph_candidates(chunks: list[EvidenceChunk]) -> GraphExtractionResult:
    provider = _graph_provider()
    batches = _chunk_batches(_select_graph_input_chunks(chunks))
    collected: list[GraphExtractionResult] = []

    for batch in batches:
        payload = provider.generate_json(
            prompt=_build_graph_prompt(batch),
            system=GRAPH_SYSTEM_PROMPT,
        )
        collected.append(GraphExtractionResult.model_validate(payload))

    return _merge_results(collected)


def extract_text_from_page_image(image_bytes: bytes, *, filename: str, page_index: int) -> str:
    provider = _vision_provider()
    prompt = (
        f"这是课堂资料 {filename} 的第 {page_index} 页。"
        "请提取页面中的正文、标题和要点。"
        "忽略纯装饰图形，返回纯文本。"
    )
    return normalize_text(
        provider.extract_text_from_image(
            image_bytes=image_bytes,
            prompt=prompt,
            system=VISION_SYSTEM_PROMPT,
        )
    )


def _graph_provider() -> OpenAICompatibleLLMProvider:
    return OpenAICompatibleLLMProvider(
        api_key=settings.graph_llm_api_key,
        base_url=settings.graph_llm_base_url,
        model=settings.graph_llm_model,
        timeout_seconds=settings.graph_llm_timeout_seconds,
    )


def _vision_provider() -> OpenAICompatibleLLMProvider:
    return OpenAICompatibleLLMProvider(
        api_key=settings.pdf_vision_api_key,
        base_url=settings.pdf_vision_base_url,
        model=settings.pdf_vision_model,
        timeout_seconds=settings.pdf_vision_timeout_seconds,
    )


def _chunk_batches(chunks: list[EvidenceChunk]) -> list[list[EvidenceChunk]]:
    batches: list[list[EvidenceChunk]] = []
    current: list[EvidenceChunk] = []
    current_chars = 0

    for chunk in chunks:
        chunk_text = _chunk_prompt_text(chunk)
        if not chunk_text:
            continue
        prompt_cost = len(chunk_text) + len(chunk.chunk_id) + 24
        if current and (
            len(current) >= settings.graph_llm_batch_max_chunks
            or current_chars + prompt_cost > settings.graph_llm_batch_max_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(chunk)
        current_chars += prompt_cost

    if current:
        batches.append(current)
    return batches


def _select_graph_input_chunks(chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
    if len(chunks) <= settings.graph_llm_max_input_units:
        return chunks

    grouped: dict[tuple[str, str], EvidenceChunk] = {}
    order: dict[tuple[str, str], tuple[int, float]] = {}

    for chunk in chunks:
        bucket = _chunk_bucket(chunk)
        key = (chunk.source_id, bucket)
        existing = grouped.get(key)
        if existing is None or _chunk_priority(chunk) > _chunk_priority(existing):
            grouped[key] = chunk
        order[key] = _chunk_order(chunk)

    representatives = sorted(grouped.values(), key=_chunk_order)
    max_units = settings.graph_llm_max_input_units
    if len(representatives) <= max_units:
        return representatives

    stride = max(1, math.ceil(len(representatives) / max_units))
    sampled = representatives[::stride]
    if representatives[-1] not in sampled:
        sampled.append(representatives[-1])
    sampled = sorted(sampled, key=_chunk_order)
    return sampled[:max_units]


def _build_graph_prompt(batch: list[EvidenceChunk]) -> str:
    lines = [
        "从下面这些 chunk 中抽取课程知识点和关系。",
        "输出 JSON object，格式如下：",
        '{',
        '  "concepts": [',
        '    {"name": "...", "canonical_name": "...", "aliases": ["..."], "definition": "...", "evidence_chunk_ids": ["chunk-1"]}',
        "  ],",
        '  "relations": [',
        '    {"source_canonical_name": "...", "target_canonical_name": "...", "edge_type": "RELATES_TO", "relation_type": "is_a", "evidence_chunk_ids": ["chunk-1"], "confidence": 0.8}',
        "  ]",
        "}",
        "要求：",
        "- 只使用输入里存在的 chunk_id 作为 evidence_chunk_ids",
        "- 同义词、中英文别名请合并到同一个概念",
        "- edge_type 只能是 RELATES_TO 或 CO_OCCURS_WITH",
        "- relation_type 只能出现在 RELATES_TO 上",
        "",
        "输入 chunks:",
    ]
    for chunk in batch:
        locator = _chunk_locator(chunk)
        lines.append(f"[{chunk.chunk_id}] ({chunk.source_type.value} {locator}) {_chunk_prompt_text(chunk)}")
    return "\n".join(lines)


def _merge_results(results: list[GraphExtractionResult]) -> GraphExtractionResult:
    concept_map: dict[str, ExtractedConcept] = {}
    relation_map: dict[tuple[str, str, str, str | None], ExtractedRelation] = {}

    for result in results:
        for concept in result.concepts:
            normalized = _normalize_concept(concept)
            if normalized is None:
                continue
            existing = concept_map.get(normalized.canonical_name)
            if existing is None:
                concept_map[normalized.canonical_name] = normalized
                continue
            merged_aliases = sorted({*existing.aliases, *normalized.aliases, existing.name, normalized.name})
            merged_evidence = list(dict.fromkeys(existing.evidence_chunk_ids + normalized.evidence_chunk_ids))
            existing.aliases = merged_aliases[:10]
            existing.evidence_chunk_ids = merged_evidence[:8]
            if len(normalized.definition) > len(existing.definition):
                existing.definition = normalized.definition
            if len(normalized.name) > len(existing.name):
                existing.name = normalized.name

        for relation in result.relations:
            normalized = _normalize_relation(relation)
            if normalized is None:
                continue
            key = (
                normalized.source_canonical_name,
                normalized.target_canonical_name,
                normalized.edge_type,
                normalized.relation_type,
            )
            existing = relation_map.get(key)
            if existing is None:
                relation_map[key] = normalized
                continue
            existing.evidence_chunk_ids = list(
                dict.fromkeys(existing.evidence_chunk_ids + normalized.evidence_chunk_ids)
            )[:8]
            existing.confidence = round(max(existing.confidence, normalized.confidence), 3)

    return GraphExtractionResult(
        concepts=sorted(concept_map.values(), key=lambda item: (len(item.evidence_chunk_ids), item.name), reverse=True),
        relations=list(relation_map.values()),
    )


def _normalize_concept(concept: ExtractedConcept) -> ExtractedConcept | None:
    name = normalize_text(concept.name)
    canonical_name = canonicalize_term(concept.canonical_name or name)
    if not canonical_name or _looks_like_noise(canonical_name):
        return None

    aliases: list[str] = []
    for alias in [name, canonical_name, *concept.aliases]:
        cleaned = normalize_text(alias)
        if not cleaned:
            continue
        cleaned_canonical = canonicalize_term(cleaned)
        if _looks_like_noise(cleaned_canonical):
            continue
        aliases.append(cleaned)

    deduped_aliases = list(dict.fromkeys(aliases))
    if not deduped_aliases:
        deduped_aliases = [name]

    definition = normalize_text(concept.definition)
    evidence_chunk_ids = list(dict.fromkeys(chunk_id.strip() for chunk_id in concept.evidence_chunk_ids if chunk_id.strip()))

    return ExtractedConcept(
        name=name or deduped_aliases[0],
        canonical_name=canonical_name,
        aliases=deduped_aliases[:10],
        definition=definition,
        evidence_chunk_ids=evidence_chunk_ids[:8],
    )


def _normalize_relation(relation: ExtractedRelation) -> ExtractedRelation | None:
    source = canonicalize_term(relation.source_canonical_name)
    target = canonicalize_term(relation.target_canonical_name)
    if not source or not target or source == target:
        return None
    if _looks_like_noise(source) or _looks_like_noise(target):
        return None

    edge_type = relation.edge_type if relation.edge_type in {item.value for item in EdgeType} else EdgeType.relates_to.value
    relation_type = normalize_text(relation.relation_type or "") or None
    if edge_type == EdgeType.relates_to.value:
        if relation_type not in VALID_RELATION_TYPES:
            return None
    else:
        relation_type = None

    return ExtractedRelation(
        source_canonical_name=source,
        target_canonical_name=target,
        edge_type=edge_type,
        relation_type=relation_type,
        evidence_chunk_ids=list(dict.fromkeys(chunk_id.strip() for chunk_id in relation.evidence_chunk_ids if chunk_id.strip()))[:8],
        confidence=max(0.0, min(float(relation.confidence), 1.0)),
    )


def _looks_like_noise(value: str) -> bool:
    if not value:
        return True
    if len(value) > 48:
        return True
    if len(value.split()) > 6:
        return True
    if any(pattern.match(value) for pattern in NOISE_PATTERNS):
        return True
    if any(fragment in value.lower() for fragment in NOISE_SUBSTRINGS):
        return True
    bare = value.replace(" ", "")
    if not is_reasonable_term(bare) and len(bare) <= 3:
        return True
    if sum(char.isdigit() for char in bare) >= max(2, len(bare) // 2):
        return True
    return False


def _chunk_locator(chunk: EvidenceChunk) -> str:
    if chunk.page_start is not None:
        return f"p.{chunk.page_start}"
    if chunk.time_start is not None:
        return f"{int(chunk.time_start // 60):02d}:{int(chunk.time_start % 60):02d}"
    return "unknown"


def _chunk_prompt_text(chunk: EvidenceChunk) -> str:
    summary = normalize_text(chunk.summary)
    text = normalize_text(chunk.text)
    if summary and summary != text:
        candidate = f"{summary} Evidence: {text[:220]}"
    else:
        candidate = text[:320]
    return candidate[:360]


def _chunk_priority(chunk: EvidenceChunk) -> float:
    summary = normalize_text(chunk.summary)
    text = normalize_text(chunk.text)
    keyword_bonus = len(chunk.keywords) * 20
    sentence_bonus = min(len(summary or text), 220)
    title_bonus = 80 if _looks_like_heading(summary or text) else 0
    return keyword_bonus + sentence_bonus + title_bonus


def _chunk_order(chunk: EvidenceChunk) -> tuple[int, float]:
    if chunk.page_start is not None:
        return (chunk.page_start, 0.0)
    if chunk.time_start is not None:
        return (10_000, chunk.time_start)
    return (99_999, 0.0)


def _chunk_bucket(chunk: EvidenceChunk) -> str:
    if chunk.page_start is not None:
        return f"page:{chunk.page_start}"
    if chunk.time_start is not None:
        return f"time:{int(chunk.time_start // 90)}"
    return f"chunk:{chunk.chunk_id}"


def _looks_like_heading(text: str) -> bool:
    compact = normalize_text(text)
    if not compact:
        return False
    if len(compact) > 80:
        return False
    lowered = compact.lower()
    return any(token in lowered for token in {"definition", "summary", "特点", "性质", "实现", "复杂度", "操作", "抽象数据类型"})
