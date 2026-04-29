from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.config import settings
from app.core.types import GenerateNotesRequest, GraphArtifact, NoteDocument, NoteSection, SessionStatus
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.services.text_utils import normalize_text
from app.storage.local import load_graph_artifact, load_note, load_session, save_note, save_session


NOTES_SYSTEM_PROMPT = """\
你是课程图谱笔记生成器。你会读取当前课程的知识图谱 JSON，并生成一份结构化学习笔记。

要求：
- 笔记必须围绕整个图谱生成，不要求用户输入主题。
- 以 topic_clusters 和概念关系组织章节，覆盖图谱中的主要知识点。
- 每节应包含概念定义、关键要点、概念之间的关系、学习顺序或易混点。
- 不输出引用、页码、来源、证据、chunk_id。
- 不要编造图谱外知识；可以用自然语言把已有 definition / summary / key_points 串成完整笔记。
- content_md 使用 Markdown，适合直接在前端阅读。
- 只返回 JSON object。
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
            content_md=normalize_text(section.content_md) or "- 暂无内容。",
            concept_ids=[concept_id for concept_id in section.concept_ids if concept_id in valid_concept_ids],
            references=[],
        )
        for section in llm_note.sections
        if normalize_text(section.title) or normalize_text(section.content_md)
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


def _generate_note_with_llm(graph: GraphArtifact, *, lecture_title: str, topic: str = "") -> LLMNoteDocument:
    if not settings.graph_llm_api_key or not settings.graph_llm_model:
        raise RuntimeError("Notes LLM is not configured. Set GRAPH_LLM_API_KEY and GRAPH_LLM_MODEL.")

    provider = OpenAICompatibleLLMProvider(
        api_key=settings.graph_llm_api_key,
        base_url=settings.graph_llm_base_url,
        model=settings.graph_llm_model,
        timeout_seconds=settings.graph_llm_timeout_seconds,
        max_output_tokens=max(settings.graph_llm_max_output_tokens, 6000),
    )
    payload = provider.generate_json(
        prompt=_build_notes_prompt(graph, lecture_title=lecture_title, topic=topic),
        system=NOTES_SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=max(settings.graph_llm_max_output_tokens, 6000),
    )
    return LLMNoteDocument.model_validate(payload)


def _build_notes_prompt(graph: GraphArtifact, *, lecture_title: str, topic: str = "") -> str:
    concept_by_id = {concept.concept_id: concept for concept in graph.concepts}
    lines = [
        f"课程讲次：{lecture_title}",
        f"用户主题偏好：{normalize_text(topic) or '无，按完整图谱生成'}",
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
    for concept in sorted(graph.concepts, key=lambda item: item.importance_score, reverse=True):
        parts = [
            f"id={concept.concept_id}",
            f"name={concept.name}",
            f"canonical={concept.canonical_name}",
        ]
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

    lines.extend(["", "关系边："])
    for edge in graph.edges:
        source = concept_by_id.get(edge.source)
        target = concept_by_id.get(edge.target)
        if source is None or target is None:
            continue
        relation_type = edge.properties.get("relation_type") or edge.edge_type
        lines.append(f"- {source.name} -> {target.name} ({relation_type})")

    lines.extend(
        [
            "",
            "生成要求：",
            "- sections 建议 3-6 节，每节 2-5 段或要点。",
            "- concept_ids 必须使用上面给出的 concept:id；如果一节覆盖多个概念，全部列入。",
            "- 不要出现“根据图谱”“根据资料来源”等元说明，直接写成课堂笔记。",
        ]
    )
    return "\n".join(lines)
