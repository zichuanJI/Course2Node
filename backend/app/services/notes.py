from __future__ import annotations

import uuid

from app.core.types import GenerateNotesRequest, NoteDocument, NoteSection, SessionStatus
from app.services.search import search_graph
from app.storage.local import load_graph_artifact, load_note, load_session, save_note, save_session


def generate_notes(request: GenerateNotesRequest) -> NoteDocument:
    graph = load_graph_artifact(request.session_id)
    session = load_session(request.session_id)

    selected_concepts = {
        concept.concept_id: concept
        for concept in graph.concepts
        if not request.concept_ids or concept.concept_id in set(request.concept_ids)
    }
    if not selected_concepts:
        search = search_graph(request.session_id, request.topic, limit=6)
        selected_ids = {hit.concept_id for hit in search.concepts}
        selected_concepts = {
            concept.concept_id: concept
            for concept in graph.concepts
            if concept.concept_id in selected_ids
        }

    if not selected_concepts:
        raise ValueError("No concepts available to generate notes.")

    sections: list[NoteSection] = []
    concept_ids = set(selected_concepts)
    for cluster in graph.topic_clusters:
        cluster_concepts = [concept_id for concept_id in cluster.concept_ids if concept_id in concept_ids]
        if not cluster_concepts:
            continue
        section_concepts = [selected_concepts[concept_id] for concept_id in cluster_concepts]
        concept_names = [concept.name for concept in section_concepts]
        paragraphs = [
            f"本节围绕 {'、'.join(concept_names[:5])} 展开。",
        ]
        for concept in section_concepts[:4]:
            paragraphs.append(f"- **{concept.name}**：{concept.definition or concept.summary or '相关知识点。'}")
        sections.append(
            NoteSection(
                title=cluster.title,
                content_md="\n".join(paragraphs),
                concept_ids=[concept.concept_id for concept in section_concepts],
                references=[],
            )
        )

    if not sections:
        concept_list = list(selected_concepts.values())[:6]
        sections = [
            NoteSection(
                title=request.topic,
                content_md="\n".join(
                    [f"- **{concept.name}**：{concept.definition or concept.summary or '相关知识点。'}" for concept in concept_list]
                ),
                concept_ids=[concept.concept_id for concept in concept_list],
                references=[],
            )
        ]

    note = NoteDocument(
        session_id=request.session_id,
        title=f"{session.lecture_title} - {request.topic}",
        topic=request.topic,
        summary=f"围绕“{request.topic}”整理出 {len(sections)} 个主题段落。",
        sections=sections,
    )
    save_note(note)
    session.status = SessionStatus.notes_ready
    save_session(session)
    return note


def get_note(session_id: uuid.UUID) -> NoteDocument:
    return load_note(session_id)

