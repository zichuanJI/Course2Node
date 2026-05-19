from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.config import settings
from app.core.types import ConceptNode, GenerateNotesRequest, GraphArtifact, GraphEdge, NoteDocument, NoteSection, SessionStatus
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
- 根据课程材料自适应组织内容，不要套固定模板，但要写出清晰的学习路径和章节递进。
- 笔记的目标不是“把图谱改写一遍”，而是帮助学生理解本讲的主线、关键概念、概念之间的连接方式，以及该如何掌握它们。
- 不输出引用、页码、来源、证据、chunk_id。
- 不要编造图谱外知识；可以用自然语言把已有 definition / summary / key_points / relationships 串成完整笔记。
- content_md 使用 Markdown，适合直接在前端阅读。
- 优先写出可学习、可复习、可直接阅读的课堂笔记，不要写成数据摘要、提纲占位符或机械拼接的百科条目。
- 只返回 JSON object。
"""

NOTE_STYLE_RULES = """\
笔记风格规则：
- 目标是“看完能掌握本讲”，不是几段概括性总结；内容要比摘要更细，解释概念在课程主线中的位置。
- 先给课程整体脉络，再按 topic_clusters 和概念关系递进展开，体现学习顺序、前置关系、相似/区别、应用位置。读者应该能顺着笔记自然地从“先懂什么”走到“再懂什么”。
- 章节标题要像老师在组织一节课，而不是把概念生硬分组。优先使用“问题导向”或“主题导向”的标题，例如“马尔可夫链如何描述状态转移”“为什么需要虚拟内存”，避免“其他概念”“补充内容”这类空泛标题。
- 每节优先回答 4 类问题中的若干项：这个概念是什么、为什么需要它、它和哪些概念构成依赖/对比/组成关系、它在课程中的作用或应用位置是什么。
- 不强制每节都有“直觉/定义/公式”。请根据原课程内容自适应：数学课重点写定义、公式、变量解释、推导关系和结论；计算机/工程课重点写概念、机制、流程、结构、操作语义和对比；文商科重点写核心概念、理论框架、案例分析、特征和影响。
- 如果图谱节点包含公式、算法或数学结论，必须使用块级 KaTeX 公式，不要用单美元 inline math，例如：
  $$
  H(X)=-\\sum_x p(x)\\log p(x)
  $$
- 不要为了形式补公式；原材料没有支撑的数学表达不要编造。
- 高 importance_score、weighted_degree_centrality、betweenness_centrality 或 closeness_centrality 的概念要写得更细；低重要度概念可以合并进相关章节。
- 每节至少说明本节概念之间如何相互连接，避免孤立罗列词条。尤其要显式写出“谁依赖谁、谁属于谁、谁用于什么、谁和谁容易混淆、谁导致什么结果”。
- 如果多个概念容易混淆，优先用简短对比表或并列条目把区别讲清楚；如果存在前置学习关系，优先写成递进链路；如果存在流程/机制，优先写成步骤或阶段。
- 当概念之间是 is_a / part_of / prerequisite_of / causes / used_for / similar_to 这类关系时，尽量在文字里把关系语义说出来，不要全部弱化成“相关”。
- 每节可以灵活使用“本节核心问题”“关键结论”“易混点”“应用场景”“小结”等小标题，但不要把所有章节写成完全一样的模板。
- 可以使用 Markdown 二级/三级标题、项目符号、表格和短小例子；不要写引用、页码、来源、证据或 chunk_id。
- Markdown 必须保留真实换行：标题单独一行，标题后空一行；列表项每条单独一行；代码块必须使用独立的三反引号起止行。
- content_md 中不要把多个标题、列表项或代码块压在同一行。
- summary 应该是对整份笔记的导读，不是简单复述 sections 标题。它要点出本讲主线、关键抓手和建议阅读顺序。
- section 的正文要有信息密度，避免一句话概述后立刻结束；也不要把 definition、summary、key_points 原样逐条复制。
- 不要出现“根据图谱”“根据资料来源”等元说明，直接写成课堂笔记。
"""

COURSE_SECTION_SYSTEM_PROMPT = """\
你是课程总笔记分章生成器。你会读取围绕某个“核心概念”及其“关联扩充节点”的局部图谱数据，并专门为这个核心主题生成结构化的一节详细笔记。

要求：
- 请围绕提供的核心主题和关联节点详细展开，把各个概念的定义、公式、相互关系交代清楚。
- 不要写总复习或整体总结，专注于写透这一个主题。
- 严格控制本节边界：已经在前文讲过的概念只做短承接，不要重复定义、重复公式或重复长段解释。
- 正文结构要清晰，像课程讲义的一节，而不是概念清单；优先组织为“本节定位 -> 核心概念 -> 关系展开 -> 易混点或应用 -> 小结”。
- content_md 必须使用 Markdown，保留正确的换行，公式使用块级 KaTeX ($$ ... $$)。
- 不要输出引用、页码、来源、证据、chunk_id。
- 只返回 JSON object，格式为：
{"title":"章节标题","content_md":"Markdown正文","concept_ids":["concept:id1", "concept:id2"]}
"""

COURSE_SUMMARY_SYSTEM_PROMPT = """\
你是课程总笔记导读生成器。你会读取课程标题和已生成的章节标题，为整本课程总笔记生成一段轻量级导读。

要求：
- 只写整份笔记的阅读导引，说明课程主线、章节之间的递进关系和建议阅读顺序。
- 不要重复输出章节正文，不要编造章节标题之外的新知识点。
- 只返回 JSON object，格式为：
{"summary":"导读正文"}
"""


class LLMNoteSection(BaseModel):
    title: str
    content_md: str
    concept_ids: list[str] = Field(default_factory=list)


class LLMNoteDocument(BaseModel):
    title: str = ""
    summary: str = ""
    sections: list[LLMNoteSection] = Field(default_factory=list)


class LLMCourseSummary(BaseModel):
    summary: str = ""


def generate_notes(request: GenerateNotesRequest) -> NoteDocument:
    graph = load_graph_artifact(request.session_id)
    session = load_session(request.session_id)
    if not graph.concepts:
        raise ValueError("No concepts available to generate notes.")

    if graph.course_meta:
        note = _generate_course_notes(request, graph, lecture_title=session.lecture_title)
    else:
        note = _generate_single_graph_notes(request, graph, lecture_title=session.lecture_title)

    save_note(note)
    session.status = SessionStatus.notes_ready
    session.updated_at = datetime.utcnow()
    session.error_message = None
    save_session(session)
    return note


def get_note(session_id: uuid.UUID) -> NoteDocument:
    return load_note(session_id)


def _generate_single_graph_notes(request: GenerateNotesRequest, graph: GraphArtifact, *, lecture_title: str) -> NoteDocument:
    llm_note = _generate_note_with_llm(graph, lecture_title=lecture_title, topic=request.topic)
    sections = _coerce_note_sections(llm_note.sections, valid_concept_ids={concept.concept_id for concept in graph.concepts})
    if not sections:
        raise ValueError("Notes LLM returned no usable sections.")

    topic = normalize_text(request.topic) or "当前知识图谱"
    return NoteDocument(
        session_id=request.session_id,
        title=normalize_text(llm_note.title) or f"{lecture_title} - 图谱笔记",
        topic=topic,
        summary=normalize_text(llm_note.summary) or f"基于当前图数据库整理出 {len(sections)} 个主题段落。",
        sections=sections,
    )


def _generate_course_notes(request: GenerateNotesRequest, graph: GraphArtifact, *, lecture_title: str) -> NoteDocument:
    course_meta = graph.course_meta
    if course_meta is None:
        raise ValueError("Course graph metadata is missing.")
    if not course_meta.core_concept_ids:
        raise ValueError("Course graph has no core concepts for note generation.")

    source_graphs = _load_source_graphs(course_meta.source_session_ids)
    topic_graphs = _build_course_topic_graphs(graph, source_graphs)
    if not topic_graphs:
        raise ValueError("Course graph produced no usable core-topic subgraphs.")

    llm_sections: list[LLMNoteSection] = []
    covered_concepts: list[str] = []
    total_sections = len(topic_graphs)
    for index, topic_graph in enumerate(topic_graphs, start=1):
        core = topic_graph.concepts[0]
        llm_sections.append(
            _generate_course_section_with_llm(
                topic_graph,
                lecture_title=lecture_title,
                topic=request.topic,
                core_concept=core,
                section_index=index,
                total_sections=total_sections,
                covered_concepts=covered_concepts,
            )
        )
        covered_concepts.extend(concept.name for concept in topic_graph.concepts)

    topic_valid_ids = {concept.concept_id for topic_graph in topic_graphs for concept in topic_graph.concepts}
    sections = _number_course_sections(_coerce_note_sections(llm_sections, valid_concept_ids=topic_valid_ids))
    if not sections:
        raise ValueError("Course notes LLM returned no usable sections.")

    section_titles = [section.title for section in sections]
    summary = _generate_course_summary_with_llm(
        graph,
        lecture_title=lecture_title,
        section_titles=section_titles,
        topic=request.topic,
    )

    topic = normalize_text(request.topic) or "课程总图谱"
    return NoteDocument(
        session_id=request.session_id,
        title=f"{lecture_title} - 课程总笔记",
        topic=topic,
        summary=normalize_text(summary) or _fallback_course_summary(section_titles),
        sections=sections,
    )


def _coerce_note_sections(llm_sections: list[LLMNoteSection], *, valid_concept_ids: set[str]) -> list[NoteSection]:
    sections: list[NoteSection] = []
    for section in llm_sections:
        if not normalize_text(section.title) and not _normalize_note_markdown(section.content_md):
            continue
        concept_ids = []
        seen_concept_ids: set[str] = set()
        for concept_id in section.concept_ids:
            if concept_id not in valid_concept_ids or concept_id in seen_concept_ids:
                continue
            concept_ids.append(concept_id)
            seen_concept_ids.add(concept_id)
        sections.append(
            NoteSection(
                title=normalize_text(section.title) or "学习笔记",
                content_md=_clean_section_markdown(section.title, section.content_md) or "- 暂无内容。",
                concept_ids=concept_ids,
                references=[],
            )
        )
    return sections


def _number_course_sections(sections: list[NoteSection]) -> list[NoteSection]:
    numbered: list[NoteSection] = []
    seen_titles: set[str] = set()
    for index, section in enumerate(sections, start=1):
        title = _strip_section_number(normalize_text(section.title)) or "核心主题"
        title_key = _heading_key(title)
        if title_key in seen_titles:
            title = f"{title}（{index}）"
        seen_titles.add(_heading_key(title))
        numbered.append(section.model_copy(update={"title": f"第 {index} 节：{title}"}))
    return numbered


def _strip_section_number(title: str) -> str:
    return re.sub(r"^第\s*\d+\s*[章节节讲课][：:、.\s-]*", "", title).strip()


def _load_source_graphs(source_session_ids: list[str]) -> list[GraphArtifact]:
    graphs: list[GraphArtifact] = []
    for session_id in source_session_ids:
        try:
            graphs.append(load_graph_artifact(uuid.UUID(session_id)))
        except (FileNotFoundError, ValueError):
            continue
    return graphs


def _build_course_topic_graphs(course_graph: GraphArtifact, source_graphs: list[GraphArtifact]) -> list[GraphArtifact]:
    course_meta = course_graph.course_meta
    if course_meta is None:
        return []

    course_by_id = {concept.concept_id: concept for concept in course_graph.concepts}
    course_by_key = _concept_lookup(course_graph.concepts)
    all_core_keys_by_id = {
        core_id: _concept_identity_keys(course_by_id[core_id])
        for core_id in course_meta.core_concept_ids
        if core_id in course_by_id
    }

    topic_graphs: list[GraphArtifact] = []
    seen_core_keys: set[str] = set()
    assigned_expansion_keys: set[str] = set()
    for core_id in course_meta.core_concept_ids:
        core = course_by_id.get(core_id)
        if core is None:
            continue
        core_key = _primary_concept_key(core)
        if core_key in seen_core_keys:
            continue
        seen_core_keys.add(core_key)

        excluded_core_keys = set().union(
            *(keys for candidate_id, keys in all_core_keys_by_id.items() if candidate_id != core_id)
        ) if all_core_keys_by_id else set()
        topic_graph = _build_enriched_topic_graph(
            course_graph,
            source_graphs,
            core,
            course_by_key=course_by_key,
            excluded_core_keys=excluded_core_keys,
            excluded_expansion_keys=assigned_expansion_keys,
        )
        if len(topic_graph.concepts) == 1:
            topic_graph = _build_fallback_topic_graph(
                course_graph,
                core,
                excluded_core_keys=excluded_core_keys,
                excluded_expansion_keys=assigned_expansion_keys,
            )
        topic_graphs.append(topic_graph)
        assigned_expansion_keys.update(_primary_concept_key(concept) for concept in topic_graph.concepts[1:])
        assigned_expansion_keys.discard("")

    return topic_graphs


def _build_enriched_topic_graph(
    course_graph: GraphArtifact,
    source_graphs: list[GraphArtifact],
    core: ConceptNode,
    *,
    course_by_key: dict[str, ConceptNode],
    excluded_core_keys: set[str],
    excluded_expansion_keys: set[str],
) -> GraphArtifact:
    core_keys = _concept_identity_keys(core)
    expansion_by_key: dict[str, ConceptNode] = {}
    edge_pool: list[GraphEdge] = []

    for source_graph in source_graphs:
        source_by_id = {concept.concept_id: concept for concept in source_graph.concepts}
        matching_core_ids = {
            concept.concept_id
            for concept in source_graph.concepts
            if core_keys & _concept_identity_keys(concept)
        }
        if not matching_core_ids:
            continue

        for edge in source_graph.edges:
            if edge.source not in source_by_id or edge.target not in source_by_id:
                continue
            edge_pool.append(edge)
            neighbor_id = ""
            if edge.source in matching_core_ids:
                neighbor_id = edge.target
            elif edge.target in matching_core_ids:
                neighbor_id = edge.source
            if not neighbor_id:
                continue

            neighbor = source_by_id[neighbor_id]
            neighbor_keys = _concept_identity_keys(neighbor)
            if neighbor_keys & core_keys or neighbor_keys & excluded_core_keys:
                continue
            key = _primary_concept_key(neighbor)
            if not key or key in excluded_expansion_keys:
                continue
            existing = expansion_by_key.get(key)
            if existing is None or neighbor.importance_score > existing.importance_score:
                expansion_by_key[key] = _map_to_course_concept(neighbor, course_by_key)

    expansions = sorted(expansion_by_key.values(), key=lambda concept: concept.importance_score, reverse=True)[:15]
    return _compose_topic_graph(course_graph, core, expansions, source_graphs, edge_pool)


def _build_fallback_topic_graph(
    course_graph: GraphArtifact,
    core: ConceptNode,
    *,
    excluded_core_keys: set[str],
    excluded_expansion_keys: set[str],
) -> GraphArtifact:
    concept_by_id = {concept.concept_id: concept for concept in course_graph.concepts}
    core_keys = _concept_identity_keys(core)
    neighbor_ids: set[str] = set()
    for edge in course_graph.edges:
        if edge.source == core.concept_id:
            neighbor_ids.add(edge.target)
        elif edge.target == core.concept_id:
            neighbor_ids.add(edge.source)

    expansions = []
    for neighbor_id in neighbor_ids:
        neighbor = concept_by_id.get(neighbor_id)
        if neighbor is None:
            continue
        neighbor_keys = _concept_identity_keys(neighbor)
        neighbor_key = _primary_concept_key(neighbor)
        if neighbor_keys & core_keys or neighbor_keys & excluded_core_keys or neighbor_key in excluded_expansion_keys:
            continue
        expansions.append(neighbor)
    expansions.sort(key=lambda concept: concept.importance_score, reverse=True)
    return _compose_topic_graph(course_graph, core, expansions[:15], [course_graph], list(course_graph.edges))


def _compose_topic_graph(
    course_graph: GraphArtifact,
    core: ConceptNode,
    expansions: list[ConceptNode],
    source_graphs: list[GraphArtifact],
    edge_pool: list[GraphEdge],
) -> GraphArtifact:
    selected = [core, *expansions]
    selected_keys = {_primary_concept_key(concept) for concept in selected}
    selected_keys.discard("")
    selected_ids = {concept.concept_id for concept in selected}
    id_to_selected_id = _selected_id_lookup(selected, source_graphs, selected_keys)

    edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str, str, str]] = set()
    for edge in edge_pool:
        mapped_source = id_to_selected_id.get(edge.source)
        mapped_target = id_to_selected_id.get(edge.target)
        if mapped_source is None or mapped_target is None or mapped_source == mapped_target:
            continue
        if mapped_source not in selected_ids or mapped_target not in selected_ids:
            continue
        relation = str(edge.properties.get("relation_type") or "")
        edge_type = edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type)
        key = (mapped_source, mapped_target, edge_type, relation)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(edge.model_copy(update={"source": mapped_source, "target": mapped_target}))

    return GraphArtifact(
        session_id=course_graph.session_id,
        concepts=selected,
        topic_clusters=[],
        edges=edges,
        course_meta=None,
    )


def _selected_id_lookup(
    selected: list[ConceptNode],
    source_graphs: list[GraphArtifact],
    selected_keys: set[str],
) -> dict[str, str]:
    selected_by_key = {_primary_concept_key(concept): concept.concept_id for concept in selected}
    lookup = {concept.concept_id: concept.concept_id for concept in selected}
    for source_graph in source_graphs:
        for concept in source_graph.concepts:
            key = _primary_concept_key(concept)
            if key in selected_keys and key in selected_by_key:
                lookup[concept.concept_id] = selected_by_key[key]
    return lookup


def _concept_lookup(concepts: list[ConceptNode]) -> dict[str, ConceptNode]:
    lookup: dict[str, ConceptNode] = {}
    for concept in concepts:
        for key in _concept_identity_keys(concept):
            lookup.setdefault(key, concept)
    return lookup


def _map_to_course_concept(concept: ConceptNode, course_by_key: dict[str, ConceptNode]) -> ConceptNode:
    for key in _concept_identity_keys(concept):
        course_concept = course_by_key.get(key)
        if course_concept is not None:
            return concept.model_copy(update={"concept_id": course_concept.concept_id})
    return concept


def _concept_identity_keys(concept: ConceptNode) -> set[str]:
    values = [concept.concept_id, concept.name, concept.canonical_name, *concept.aliases]
    return {_normalize_concept_key(value) for value in values if _normalize_concept_key(value)}


def _primary_concept_key(concept: ConceptNode) -> str:
    return _normalize_concept_key(concept.canonical_name) or _normalize_concept_key(concept.name) or concept.concept_id


def _normalize_concept_key(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalize_text(value)).lower()


def _fallback_course_summary(section_titles: list[str]) -> str:
    if not section_titles:
        return "这份课程总笔记按核心概念组织章节，适合先把握主线，再逐节深入复习。"
    return "这份课程总笔记围绕核心概念展开，建议按章节顺序阅读：" + "、".join(section_titles) + "。"


def _format_covered_concepts(concepts: list[str], *, limit: int = 24) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for concept in concepts:
        name = normalize_text(concept)
        key = _normalize_concept_key(name)
        if not name or key in seen:
            continue
        unique.append(name)
        seen.add(key)
        if len(unique) >= limit:
            break
    return "、".join(unique) if unique else "无"


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
    provider = _make_notes_provider()
    payload = provider.generate_json(
        prompt=_build_notes_prompt(graph, lecture_title=lecture_title, topic=topic),
        system=NOTES_SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=max(settings.graph_llm_max_output_tokens, NOTES_MIN_OUTPUT_TOKENS),
    )
    return LLMNoteDocument.model_validate(payload)


def _generate_course_section_with_llm(
    topic_graph: GraphArtifact,
    *,
    lecture_title: str,
    topic: str,
    core_concept: ConceptNode,
    section_index: int,
    total_sections: int,
    covered_concepts: list[str],
) -> LLMNoteSection:
    provider = _make_notes_provider()
    payload = provider.generate_json(
        prompt=_build_course_section_prompt(
            topic_graph,
            lecture_title=lecture_title,
            topic=topic,
            core_concept=core_concept,
            section_index=section_index,
            total_sections=total_sections,
            covered_concepts=covered_concepts,
        ),
        system=COURSE_SECTION_SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=max(settings.graph_llm_max_output_tokens, NOTES_MIN_OUTPUT_TOKENS),
    )
    return LLMNoteSection.model_validate(payload)


def _generate_course_summary_with_llm(
    graph: GraphArtifact,
    *,
    lecture_title: str,
    section_titles: list[str],
    topic: str,
) -> str:
    provider = _make_notes_provider(max_output_tokens=1200)
    payload = provider.generate_json(
        prompt=_build_course_summary_prompt(
            graph,
            lecture_title=lecture_title,
            section_titles=section_titles,
            topic=topic,
        ),
        system=COURSE_SUMMARY_SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=1200,
    )
    return LLMCourseSummary.model_validate(payload).summary


def _make_notes_provider(*, max_output_tokens: int | None = None) -> OpenAICompatibleLLMProvider:
    if not settings.graph_llm_api_key or not settings.graph_llm_model:
        raise RuntimeError("Notes LLM is not configured. Set GRAPH_LLM_API_KEY and GRAPH_LLM_MODEL.")

    return OpenAICompatibleLLMProvider(
        api_key=settings.graph_llm_api_key,
        base_url=settings.graph_llm_base_url,
        model=settings.graph_llm_model,
        timeout_seconds=max(settings.graph_llm_timeout_seconds, NOTES_MIN_TIMEOUT_SECONDS),
        max_output_tokens=max_output_tokens or max(settings.graph_llm_max_output_tokens, NOTES_MIN_OUTPUT_TOKENS),
    )


def _build_course_section_prompt(
    topic_graph: GraphArtifact,
    *,
    lecture_title: str,
    topic: str,
    core_concept: ConceptNode,
    section_index: int,
    total_sections: int,
    covered_concepts: list[str],
) -> str:
    concept_by_id = {concept.concept_id: concept for concept in topic_graph.concepts}
    lines = [
        f"课程总图谱：{lecture_title}",
        f"用户主题偏好：{normalize_text(topic) or '无，按课程总图谱生成'}",
        f"章节位置：第 {section_index} 节 / 共 {total_sections} 节",
        f"section_index={section_index}/{total_sections}",
        f"本节核心概念：{core_concept.name}",
        f"前文已重点讲过的概念：{_format_covered_concepts(covered_concepts)}",
        f"already_covered_concepts={_format_covered_concepts(covered_concepts)}",
        "",
        NOTE_STYLE_RULES.strip(),
        "",
        "输出结构：",
        '{"title":"","content_md":"","concept_ids":["concept:id"]}',
        "",
        "局部强化图谱：",
        "这一组数据由 1 个核心节点 + 最多 15 个直接关联扩充节点组成，来自原始 PDF 子图谱的关联扩充知识库。",
        "",
        "节点：",
    ]
    for index, concept in enumerate(topic_graph.concepts):
        role = "core" if index == 0 else "neighbor"
        parts = [
            f"role={role}",
            f"id={concept.concept_id}",
            f"name={concept.name}",
            f"canonical={concept.canonical_name}",
            f"importance_score={concept.importance_score:.4f}",
        ]
        if concept.graph_metrics:
            parts.append(
                "graph_metrics="
                + "；".join(f"{key}={value:.4f}" for key, value in sorted(concept.graph_metrics.items()))
            )
        if concept.definition:
            parts.append(f"definition={concept.definition[:260]}")
        if concept.summary:
            parts.append(f"summary={concept.summary[:320]}")
        if concept.key_points:
            parts.append(f"key_points={'；'.join(concept.key_points[:6])}")
        if concept.prerequisites:
            parts.append(f"prerequisites={'；'.join(concept.prerequisites[:6])}")
        if concept.applications:
            parts.append(f"applications={'；'.join(concept.applications[:6])}")
        lines.append("- " + " | ".join(parts))

    lines.extend(["", "关系边："])
    for edge in topic_graph.edges:
        source = concept_by_id.get(edge.source)
        target = concept_by_id.get(edge.target)
        if source is None or target is None:
            continue
        relation_type = edge.properties.get("relation_type") or edge.edge_type
        lines.append(f"- {source.name} -> {target.name} ({relation_type})")
    if not topic_graph.edges:
        lines.append("- 无显式关系边时，请根据节点定义和 key_points 组织本节，但不要编造图谱外知识。")

    lines.extend(
        [
            "",
            "生成要求：",
            f"- title 必须是“第 {section_index} 节：...”风格的主题标题，聚焦本节核心概念，不要使用泛泛的“课程总结/综合复习/核心概念”。",
            "- 只生成这一节，不要生成整本课程总览、导读或结语。",
            "- 正文请按清晰讲义结构组织，优先使用这些二级小标题：本节定位、核心概念、关系展开、易混点或应用、小结。",
            "- 本节只详细展开上面“节点”列表中的概念；前文已重点讲过的概念如果必须出现，只用一句话承接，不要再次写定义、公式或长段解释。",
            "- 内容要围绕核心概念展开，并把关联节点写成解释、对比、前置关系、组成关系或应用位置，避免把同一批概念反复列成相同段落。",
            "- concept_ids 必须使用上面给出的 id；至少包含核心概念 id，且不要重复。",
        ]
    )
    return "\n".join(lines)


def _build_course_summary_prompt(
    graph: GraphArtifact,
    *,
    lecture_title: str,
    section_titles: list[str],
    topic: str,
) -> str:
    core_names = []
    concept_by_id = {concept.concept_id: concept for concept in graph.concepts}
    if graph.course_meta:
        core_names = [
            concept_by_id[concept_id].name
            for concept_id in graph.course_meta.core_concept_ids
            if concept_id in concept_by_id
        ]

    lines = [
        f"课程：{lecture_title}",
        f"用户主题偏好：{normalize_text(topic) or '无'}",
        "",
        "核心概念：",
    ]
    lines.extend(f"- {name}" for name in core_names)
    lines.extend(["", "已经生成的章节标题："])
    lines.extend(f"{index}. {title}" for index, title in enumerate(section_titles, start=1))
    lines.extend(
        [
            "",
            "请生成整本课程总笔记的导读 summary，1-2 段即可，重点说明阅读顺序和章节主线。",
            "只返回 JSON：",
            '{"summary":""}',
        ]
    )
    return "\n".join(lines)


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
        "输出结构说明：",
        "- 返回 JSON object，字段固定为 title、summary、sections。",
        "- title 是这份笔记的标题，要自然、明确，像课程讲义标题。",
        "- summary 是整份笔记的导读，建议 1-2 段，说明主线、重点和阅读路径。",
        "- sections 是主体内容；每节都要有足够展开的 content_md，不能只写几句空泛概括。",
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
    lines.extend(
        [
            "- 关系语义参考：is_a=属于/分类关系，part_of=组成部分，prerequisite_of=前置依赖，causes=导致/影响，used_for=用于/服务于，similar_to=相似或易混淆。",
            "- 写笔记时优先把这些关系转成教学语言，例如“先理解 A，才能理解 B”“A 是 B 的组成部分”“A 常用于 B”“A 与 B 容易混淆，但区别在于……”。",
        ]
    )
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
            "- 笔记整体要有一条明显主线：先总览，再展开核心概念，再补充关系、区别、应用和约束，最后形成可复习的收束。",
            "- 每节正文优先围绕“概念解释 + 关系组织 + 学习作用”展开，而不是只堆砌定义。",
            "- 若一节中存在明显的对比、分类、流程、约束或用途，请优先使用列表、表格或小标题，让信息结构清晰可扫读。",
            "- 对高重要度概念，尽量写出：定义/直觉、和其他概念的连接、为什么重要、常见误区或典型应用中的至少两三项。",
            "- 如果图谱里能看出前置链路，请在章节顺序和行文中显式体现；不要把后置概念放在前置概念之前硬讲。",
            "- concept_ids 必须使用上面给出的 concept:id；如果一节覆盖多个概念，全部列入。",
            "- 优先展开 importance_score 和图指标较高的概念，但不要遗漏支撑课程主线的普通概念。",
            "- 不要输出空洞结尾，不要出现“以上就是本节内容”这类无信息量句子；收尾应帮助复习或串联下一节。",
        ]
    )
    return "\n".join(lines)
