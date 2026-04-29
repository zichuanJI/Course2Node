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

核心目标：
- 输出“课程核心概念主图”，不是原文索引，也不是词频表。
- 节点质量优先于节点数量；宁可漏掉边缘概念，也不要把噪声节点放进主图。
- 优先覆盖章节主线概念，而不是覆盖全部文本。

只保留真正可教学的知识点：
- 概念、术语、定义、方法、模型、结构、规则、约束、操作
- 运算名、完整性类别、查询方法、模式、语言
- 关键术语的中英文表达或缩写

直接剔除：
- 页眉页脚、目录残片、章节号、页码、表号、小结、学习目标
- 示例数据、表格示例值、纯案例中的记录值
- 人名、学号、课程号、专业号、姓名、性别、年龄等字段型属性名
- 只在例子里有意义的实体，即使频率高也不要保留
- “关系数据结构及形式化定义”这类章节标题不能直接作为概念，必须拆成真正概念

关系限制：
- RELATES_TO 只能用于明确、可解释的语义关系
- relation_type 只能是 is_a / part_of / prerequisite_of / causes / used_for / similar_to
- CO_OCCURS_WITH 仅表示高频共现，不表示明确语义
- 不要为了连通性补边；没有明确语义依据就不要输出关系
- 不输出引用、页码、来源说明、chunk_id 或 evidence 字段

节点要求：
- 每个概念都要像一个可展开的小型学习卡片，而不只是一个词条。
- definition: 用一句准确的话解释概念，尽量忠实于输入文本，不要扩写无根据内容。
- summary: 用 1-2 句话总结这个概念在本讲中的作用或位置。
- key_points: 给 2-4 条要点，适合在节点抽屉中直接阅读。
- tags: 给 2-5 个短标签，如“线性结构”“复杂度”“实现”。
- prerequisites: 仅保留本讲中真正先于它、理解它所需的前置概念名。
- applications: 仅保留本讲中提到的用途、适用场景或典型操作。

同义归一化：
- 中英文写法、缩写、全称必须合并到一个概念。
- name 取最自然的展示名；canonical_name 取规范名；aliases 收集常见写法。
- 不要输出两个只差大小写、单复数、中文/英文翻译的重复节点。

规模要求：
- 对当前输入 batch 中出现的可教学知识点尽量完整抽取，不做全局数量截断。
- 每个 batch 的关系保持可解释，优先保留明确语义边，再保留强共现边。

质量自检：
- 图里是否主要都是可教学概念？
- 节点定义是否简洁准确？
- 关系类型是否可解释？
- 是否出现明显噪声团或毛线球倾向？如果有，删掉低价值节点和边。

输出必须是 JSON object。不要输出引用、页码、来源、chunk_id、evidence_chunk_ids。
"""

NOISE_PATTERNS = [
    re.compile(r"^\d+(\.\d+)+$"),
    re.compile(r"^(chapter|section|lecture|slide)\b", re.IGNORECASE),
    re.compile(r"^第[一二三四五六七八九十百\d]+[章节讲]$"),
    re.compile(r"^表\s*\d+(\.\d+)*$"),
    re.compile(r"^dbch\d+$", re.IGNORECASE),
]
NOISE_SUBSTRINGS = {
    "本章",
    "主要内容",
    "本节",
    "目录",
    "contents",
    "outline",
    "example",
    "learning objective",
    "学习目标",
    "小结",
    "student",
    "学号",
    "课程号",
    "专业号",
    "姓名",
    "性别",
    "年龄",
    "张清玫",
    "刘逸",
    "李勇",
    "刘晨",
    "王敏",
    "信息专业",
    "计算机专业",
    "关系数据结构及形式化定义",
    "page",
}
VALID_RELATION_TYPES = {item.value for item in RelationType}


class ExtractedConcept(BaseModel):
    name: str
    canonical_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
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


def extract_graph_candidates(chunks: list[EvidenceChunk]) -> GraphExtractionResult:
    provider = _graph_provider()
    batches = _chunk_batches(_select_graph_input_chunks(chunks))
    collected: list[GraphExtractionResult] = []

    for batch in batches:
        collected.extend(_extract_batch_candidates(provider, batch))

    return _merge_results(collected)


def _extract_batch_candidates(
    provider: OpenAICompatibleLLMProvider,
    batch: list[EvidenceChunk],
) -> list[GraphExtractionResult]:
    try:
        payload = provider.generate_json(
            prompt=_build_graph_prompt(batch),
            system=GRAPH_SYSTEM_PROMPT,
        )
        return [GraphExtractionResult.model_validate(payload)]
    except ValueError as exc:
        if not _looks_like_truncated_json_error(exc):
            raise
        if len(batch) > 1:
            midpoint = max(1, len(batch) // 2)
            return [
                *_extract_batch_candidates(provider, batch[:midpoint]),
                *_extract_batch_candidates(provider, batch[midpoint:]),
            ]
        payload = provider.generate_json(
            prompt=_build_compact_graph_prompt(batch),
            system=GRAPH_SYSTEM_PROMPT,
            max_output_tokens=max(settings.graph_llm_max_output_tokens, 4200),
        )
        return [GraphExtractionResult.model_validate(payload)]


def _graph_provider() -> OpenAICompatibleLLMProvider:
    return OpenAICompatibleLLMProvider(
        api_key=settings.graph_llm_api_key,
        base_url=settings.graph_llm_base_url,
        model=settings.graph_llm_model,
        timeout_seconds=settings.graph_llm_timeout_seconds,
        max_output_tokens=settings.graph_llm_max_output_tokens,
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
    cleaned_chunks = [chunk for chunk in chunks if not _is_low_signal_chunk(chunk)]
    if not cleaned_chunks:
        cleaned_chunks = chunks

    max_units = settings.graph_llm_max_input_units
    if max_units <= 0:
        return cleaned_chunks
    if len(cleaned_chunks) <= max_units:
        return cleaned_chunks

    grouped: dict[tuple[str, str], EvidenceChunk] = {}
    order: dict[tuple[str, str], tuple[int, float]] = {}

    for chunk in cleaned_chunks:
        bucket = _chunk_bucket(chunk)
        key = (chunk.source_id, bucket)
        existing = grouped.get(key)
        if existing is None or _chunk_priority(chunk) > _chunk_priority(existing):
            grouped[key] = chunk
        order[key] = _chunk_order(chunk)

    representatives = sorted(grouped.values(), key=_chunk_order)
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
        "从下面这些文本片段中抽取课程知识点和关系。",
        "先按以下清洗流程在内部筛选：候选概念 -> 噪声剔除 -> 同义归一化 -> 定义生成 -> 稀疏关系抽取。",
        "输出 JSON object，格式如下：",
        '{',
        '  "concepts": [',
        '    {"name": "...", "canonical_name": "...", "aliases": ["..."], "definition": "...", "summary": "...", "key_points": ["..."], "tags": ["..."], "prerequisites": ["..."], "applications": ["..."]}',
        "  ],",
        '  "relations": [',
        '    {"source_canonical_name": "...", "target_canonical_name": "...", "edge_type": "RELATES_TO", "relation_type": "is_a", "confidence": 0.8}',
        "  ]",
        "}",
        "要求：",
        "- 不要输出 evidence_chunk_ids、chunk_id、页码、引用或来源说明",
        "- 同义词、中英文别名请合并到同一个概念",
        "- 优先抽标题、定义句、枚举项、运算名、约束名、模型名中的核心概念",
        "- 默认丢弃人名、学号、课程号、专业号、姓名、性别、年龄、表格示例值、页码和章节编号",
        "- 如果一个词只是例子里的字段或记录值，不要输出为概念",
        "- definition 必须是一句教学定义；summary/key_points 要能作为节点小笔记阅读",
        "- edge_type 只能是 RELATES_TO 或 CO_OCCURS_WITH",
        "- relation_type 只能出现在 RELATES_TO 上",
        "- RELATES_TO 必须有明确语义，CO_OCCURS_WITH 只在强共现时使用",
        "- 对当前 batch 中出现的可教学知识点尽量完整抽取，不要因为全局数量限制丢掉有效知识点",
        "- 若当前 batch 知识点很多，优先保留有定义、操作、公式、约束、模型或方法说明的概念",
        "- 为避免输出过长，每个字符串字段尽量控制在 90 个中文字符以内",
        "- key_points 最多 3 条，tags 最多 4 个，prerequisites/applications 没有明确文本依据时返回空数组",
        "- 关系数据库类章节的保留范式示例：关系模型、关系、域、笛卡尔积、元组、属性、候选码、主码、外码、关系模式、关系操作、选择、投影、连接、关系完整性、SQL",
        "",
        "输入文本片段:",
    ]
    for index, chunk in enumerate(batch, start=1):
        lines.append(f"片段 {index}: {_chunk_prompt_text(chunk)}")
    return "\n".join(lines)


def _build_compact_graph_prompt(batch: list[EvidenceChunk]) -> str:
    lines = [
        "上一次 JSON 输出过长或被截断。请重新抽取更小、更紧凑的课程知识图谱。",
        "只输出 JSON object，不要 markdown，不要解释。",
        "格式：",
        '{"concepts":[{"name":"","canonical_name":"","aliases":[],"definition":"","summary":"","key_points":[],"tags":[],"prerequisites":[],"applications":[]}],"relations":[{"source_canonical_name":"","target_canonical_name":"","edge_type":"RELATES_TO","relation_type":"used_for","confidence":0.8}]}',
        "硬性限制：",
        "- concepts 最多 6 个，只选章节主线概念",
        "- relations 最多 8 条，只保留最明确的语义关系",
        "- definition/summary 每项不超过 45 个中文字符",
        "- key_points 最多 2 条，每条不超过 30 个中文字符",
        "- tags 最多 3 个",
        "- prerequisites/applications 没有明确文本依据时返回空数组",
        "- 不要输出 evidence_chunk_ids、chunk_id、页码、引用或来源说明",
        "",
        "输入文本片段:",
    ]
    for index, chunk in enumerate(batch, start=1):
        lines.append(f"片段 {index}: {_chunk_prompt_text(chunk)[:260]}")
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
            existing.aliases = merged_aliases[:10]
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
            existing.confidence = round(max(existing.confidence, normalized.confidence), 3)

    return GraphExtractionResult(
        concepts=sorted(concept_map.values(), key=lambda item: item.name),
        relations=list(relation_map.values()),
    )


def _looks_like_truncated_json_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "model did not return valid json" not in message:
        return False
    return any(token in message for token in {"unterminated", "expecting", "delimiter", "valid json"})


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
    summary = normalize_text(concept.summary)
    return ExtractedConcept(
        name=name or deduped_aliases[0],
        canonical_name=canonical_name,
        aliases=deduped_aliases[:10],
        definition=definition,
        summary=summary,
        key_points=_clean_short_lines(concept.key_points, max_items=4),
        tags=_clean_short_lines(concept.tags, max_items=5),
        prerequisites=_clean_short_lines(concept.prerequisites, max_items=4),
        applications=_clean_short_lines(concept.applications, max_items=4),
        evidence_chunk_ids=[],
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
        evidence_chunk_ids=[],
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


def _chunk_prompt_text(chunk: EvidenceChunk) -> str:
    summary = normalize_text(chunk.summary)
    text = normalize_text(chunk.text)
    if summary and summary != text:
        candidate = f"{summary} 内容: {text[:220]}"
    else:
        candidate = text[:320]
    return candidate[:360]


def _clean_short_lines(items: list[str], *, max_items: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = normalize_text(item)
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(value[:120])
        if len(cleaned) >= max_items:
            break
    return cleaned


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


def _is_low_signal_chunk(chunk: EvidenceChunk) -> bool:
    text = normalize_text(chunk.text)
    lowered = text.lower()
    if chunk.source_type.value == "audio" and lowered.startswith("asr failed for "):
        return True
    if len(text) < 24:
        return True
    if text.count("知识点") >= 3:
        return True
    if any(token in lowered for token in {"本节授课大纲", "section 2.", "学习目标", "课堂纪律", "南京大学信息管理学院"}):
        return True
    if re.fullmatch(r"[\d\.\s\-:：a-zA-Z一二三四五六七八九十]+", text) and len(text) < 80:
        return True
    return False
