from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.config import settings
from app.core.types import GenerateNotesRequest, GraphArtifact, NoteDocument, NoteSection, SessionStatus
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.services.text_utils import normalize_text
from app.storage.local import load_graph_artifact, load_note, load_session, save_note, save_session

NOTES_DETAILED_CONCEPT_LIMIT = 48
NOTES_MAX_EDGE_LINES = 100
NOTES_MIN_TIMEOUT_SECONDS = 120.0
NOTES_MIN_OUTPUT_TOKENS = 8000


NOTES_SYSTEM_PROMPT = """\
你是课程图谱笔记生成器。你会读取当前课程的知识图谱 JSON，并生成一份结构化学习笔记。

要求：
- 笔记必须围绕整个图谱生成，不要求用户输入主题。
- 以 topic_clusters、概念关系和图指标组织章节，覆盖图谱中的主要知识点。
- 根据课程材料自适应组织内容，不要套固定模板。
- 不输出引用、页码、来源、证据、chunk_id。
- 不要编造图谱外知识；可以用自然语言把已有 definition / summary / key_points / relationships 串成完整笔记。
- content_md 使用 Markdown，适合直接在前端阅读。
- 只返回 JSON object。
"""

NOTE_STYLE_RULES = """\
笔记风格规则：
- 目标是“看完能掌握本讲”，不是几段概括性总结；内容要比摘要更细，解释概念在课程主线中的位置。
- 先给课程整体脉络，再按 topic_clusters 和概念关系递进展开，体现学习顺序、前置关系、相似/区别、应用位置。
- 不强制每节都有“直觉/定义/公式”。请根据原课程内容自适应：数学课重点写定义、公式、变量解释、推导关系和结论；数据库/系统/网络课重点写概念、机制、流程、结构、约束、操作语义、对比关系和典型场景。
- 如果图谱节点包含公式、算法或数学结论，必须使用块级 KaTeX 公式，不要用单美元 inline math，例如：
  $$
  H(X)=-\\sum_x p(x)\\log p(x)
  $$
- 不要为了形式补公式；原材料没有支撑的数学表达不要编造。
- 高 importance_score、weighted_degree_centrality、betweenness_centrality 或 closeness_centrality 的概念要写得更细；低重要度概念可以合并进相关章节。
- 每节至少说明本节概念之间如何相互连接，避免孤立罗列词条。
- 可以使用 Markdown 二级/三级标题、项目符号、表格和短小例子；不要写引用、页码、来源、证据或 chunk_id。
- Markdown 必须保留真实换行：标题单独一行，标题后空一行；列表项每条单独一行；代码块必须使用独立的三反引号起止行。
- content_md 中不要把多个标题、列表项或代码块压在同一行。
- 不要出现“根据图谱”“根据资料来源”等元说明，直接写成课堂笔记。
"""


class LLMNoteSection(BaseModel):
    title: str
    content_md: str
    concept_ids: list[str] = Field(default_factory=list)


class LLMNoteDocument(BaseModel):
    title: str = ""
    summary: str = ""
    sections: list[LLMNoteSection] = Field(default_factory=list)


def generate_notes(request: GenerateNotesRequest) -> NoteDocument:
    graph = load_graph_artifact(request.session_id)
    session = load_session(request.session_id)
    if not graph.concepts:
        raise ValueError("No concepts available to generate notes.")

    llm_note = _generate_note_with_llm(graph, lecture_title=session.lecture_title, topic=request.topic)
    valid_concept_ids = {concept.concept_id for concept in graph.concepts}
    sections = [
        NoteSection(
            title=normalize_text(section.title) or "学习笔记",
            content_md=_clean_section_markdown(section.title, section.content_md) or "- 暂无内容。",
            concept_ids=[concept_id for concept_id in section.concept_ids if concept_id in valid_concept_ids],
            references=[],
        )
        for section in llm_note.sections
        if normalize_text(section.title) or _normalize_note_markdown(section.content_md)
    ]
    if not sections:
        raise ValueError("Notes LLM returned no usable sections.")

    topic = normalize_text(request.topic) or "当前知识图谱"
    note = NoteDocument(
        session_id=request.session_id,
        title=normalize_text(llm_note.title) or f"{session.lecture_title} - 图谱笔记",
        topic=topic,
        summary=normalize_text(llm_note.summary) or f"基于当前图数据库整理出 {len(sections)} 个主题段落。",
        sections=sections,
    )
    save_note(note)
    session.status = SessionStatus.notes_ready
    session.updated_at = datetime.utcnow()
    session.error_message = None
    save_session(session)
    return note


def get_note(session_id: uuid.UUID) -> NoteDocument:
    return load_note(session_id)


def _normalize_note_markdown(text: str) -> str:
    markdown = text.replace("\\n", "\n").replace("\\r", "\n").replace("\\t", "  ")
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    if _markdown_looks_collapsed(markdown):
        markdown = _restore_markdown_breaks(markdown)
    return markdown.strip()


def _clean_section_markdown(title: str, content_md: str) -> str:
    markdown = _normalize_note_markdown(content_md)
    return _remove_duplicate_section_heading(title, markdown)


def _remove_duplicate_section_heading(title: str, markdown: str) -> str:
    normalized_title = _heading_key(title)
    if not normalized_title:
        return markdown
    lines = markdown.splitlines()
    if not lines:
        return markdown
    match = re.match(r"^#{1,6}\s+(.+?)\s*$", lines[0])
    if not match:
        return markdown
    if _heading_key(match.group(1)) != normalized_title:
        return markdown
    remaining = lines[1:]
    while remaining and not remaining[0].strip():
        remaining.pop(0)
    return "\n".join(remaining).strip()


def _heading_key(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalize_text(text)).lower()


def _markdown_looks_collapsed(markdown: str) -> bool:
    stripped = markdown.strip()
    if not stripped:
        return False
    if "\n" not in stripped:
        return bool(re.search(r"(#{2,6}\s+| - |\s```)", stripped))
    return any(
        len(line) > 220 and re.search(r"(#{2,6}\s+| - |\s```)", line)
        for line in stripped.splitlines()
    )


def _restore_markdown_breaks(markdown: str) -> str:
    text = re.sub(r"\s+", " ", markdown.strip())

    def code_block_replacer(match: re.Match[str]) -> str:
        language = match.group(1).strip()
        body = match.group(2).strip()
        return f"\n\n```{language}\n{body}\n```\n\n"

    text = re.sub(r"```([A-Za-z0-9_-]*)\s+(.*?)\s+```", code_block_replacer, text)
    text = re.sub(r"\s+(#{2,6}\s+)", r"\n\n\1", text)
    text = re.sub(r"\s+-\s+(\*\*|`|[A-Za-z0-9\u4e00-\u9fff])", r"\n- \1", text)
    text = re.sub(r"\s+(\d+\.\s+)", r"\n\1", text)

    lines = [_split_collapsed_heading(line.strip()) for line in text.splitlines()]
    restored = "\n".join(line for line in lines if line)
    restored = re.sub(r"(?m)^(#{2,6}\s+.+)\n(?!\n)", r"\1\n\n", restored)
    restored = re.sub(r"(?m)([^\n])\n(#{2,6}\s+)", r"\1\n\n\2", restored)
    restored = re.sub(r"(?m)([^\n])\n(-\s+)", r"\1\n\n\2", restored)
    restored = re.sub(r"\n{3,}", "\n\n", restored)
    return restored.strip()


def _split_collapsed_heading(line: str) -> str:
    match = re.match(r"^(#{2,6}\s+)(.+)$", line)
    if not match:
        return line
    prefix, content = match.groups()

    title, separator, rest = content.partition(" ")
    if separator and 2 <= len(title) <= 28 and _contains_cjk(title):
        return f"{prefix}{title}\n\n{rest.strip()}"

    for marker in (" ```", " - ", " 1. "):
        index = content.find(marker)
        if 2 <= index <= 40:
            return f"{prefix}{content[:index].strip()}\n\n{content[index:].strip()}"
    return line


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _generate_note_with_llm(graph: GraphArtifact, *, lecture_title: str, topic: str = "") -> LLMNoteDocument:
    if not settings.graph_llm_api_key or not settings.graph_llm_model:
        raise RuntimeError("Notes LLM is not configured. Set GRAPH_LLM_API_KEY and GRAPH_LLM_MODEL.")

    provider = OpenAICompatibleLLMProvider(
        api_key=settings.graph_llm_api_key,
        base_url=settings.graph_llm_base_url,
        model=settings.graph_llm_model,
        timeout_seconds=max(settings.graph_llm_timeout_seconds, NOTES_MIN_TIMEOUT_SECONDS),
        max_output_tokens=max(settings.graph_llm_max_output_tokens, NOTES_MIN_OUTPUT_TOKENS),
    )
    payload = provider.generate_json(
        prompt=_build_notes_prompt(graph, lecture_title=lecture_title, topic=topic),
        system=NOTES_SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=max(settings.graph_llm_max_output_tokens, NOTES_MIN_OUTPUT_TOKENS),
    )
    return LLMNoteDocument.model_validate(payload)


def _build_notes_prompt(graph: GraphArtifact, *, lecture_title: str, topic: str = "") -> str:
    concept_by_id = {concept.concept_id: concept for concept in graph.concepts}
    sorted_concepts = sorted(graph.concepts, key=lambda item: item.importance_score, reverse=True)
    detailed_concepts = sorted_concepts[:NOTES_DETAILED_CONCEPT_LIMIT]
    detailed_ids = {concept.concept_id for concept in detailed_concepts}
    lines = [
        f"课程讲次：{lecture_title}",
        f"用户主题偏好：{normalize_text(topic) or '无，按完整图谱生成'}",
        "",
        NOTE_STYLE_RULES.strip(),
        "",
        "请输出 JSON：",
        '{"title":"","summary":"","sections":[{"title":"","content_md":"","concept_ids":["concept:id"]}]}',
        "",
        "图谱聚类：",
    ]

    for cluster in graph.topic_clusters:
        concept_names = [
            concept_by_id[concept_id].name
            for concept_id in cluster.concept_ids
            if concept_id in concept_by_id
        ]
        lines.append(f"- {cluster.cluster_id} {cluster.title}: {'、'.join(concept_names)}")

    lines.extend(["", "概念节点："])
    lines.append("以下是高重要度概念，需要优先详细展开：")
    for concept in detailed_concepts:
        parts = [
            f"id={concept.concept_id}",
            f"name={concept.name}",
            f"canonical={concept.canonical_name}",
            f"importance_score={concept.importance_score:.4f}",
        ]
        if concept.graph_metrics:
            metrics = "，".join(
                f"{key}={value:.4f}"
                for key, value in sorted(concept.graph_metrics.items())
            )
            parts.append(f"graph_metrics={metrics}")
        if concept.definition:
            parts.append(f"definition={concept.definition[:180]}")
        if concept.summary:
            parts.append(f"summary={concept.summary[:220]}")
        if concept.key_points:
            parts.append(f"key_points={'；'.join(concept.key_points[:4])}")
        if concept.prerequisites:
            parts.append(f"prerequisites={'、'.join(concept.prerequisites[:4])}")
        if concept.applications:
            parts.append(f"applications={'、'.join(concept.applications[:4])}")
        lines.append("- " + " | ".join(parts))

    remaining_concepts = [concept for concept in sorted_concepts if concept.concept_id not in detailed_ids]
    if remaining_concepts:
        lines.extend(["", "其余概念目录："])
        for concept in remaining_concepts:
            parts = [
                f"id={concept.concept_id}",
                f"name={concept.name}",
                f"importance_score={concept.importance_score:.4f}",
            ]
            if concept.definition:
                parts.append(f"definition={concept.definition[:80]}")
            lines.append("- " + " | ".join(parts))

    lines.extend(["", "关系边（按重要性截取，优先用于组织章节和学习路径）："])
    ranked_edges = sorted(
        graph.edges,
        key=lambda edge: (
            concept_by_id.get(edge.source).importance_score if concept_by_id.get(edge.source) else 0.0
        )
        + (
            concept_by_id.get(edge.target).importance_score if concept_by_id.get(edge.target) else 0.0
        ),
        reverse=True,
    )
    for edge in ranked_edges[:NOTES_MAX_EDGE_LINES]:
        source = concept_by_id.get(edge.source)
        target = concept_by_id.get(edge.target)
        if source is None or target is None:
            continue
        relation_type = edge.properties.get("relation_type") or edge.edge_type
        lines.append(f"- {source.name} -> {target.name} ({relation_type})")
    if len(graph.edges) > NOTES_MAX_EDGE_LINES:
        lines.append(f"- 其余 {len(graph.edges) - NOTES_MAX_EDGE_LINES} 条低优先级关系可作为背景，不必逐条展开。")

    lines.extend(
        [
            "",
            "生成要求：",
            "- sections 建议 4-8 节；重要章节可以更细，低重要度知识点合并到相关章节。",
            "- concept_ids 必须使用上面给出的 concept:id；如果一节覆盖多个概念，全部列入。",
            "- 优先展开 importance_score 和图指标较高的概念，但不要遗漏支撑课程主线的普通概念。",
        ]
    )
    return "\n".join(lines)
