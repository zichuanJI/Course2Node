from __future__ import annotations

import uuid
from collections import deque

from app.services.embeddings import embed_query
from app.core.types import (
    EdgeType,
    SearchChunkHit,
    SearchConceptHit,
    SearchResponse,
    SubgraphEdge,
    SubgraphNode,
    SubgraphResponse,
)
from app.services.text_utils import best_snippet, cosine_similarity, extract_candidate_terms
from app.storage.local import list_ingest_artifacts, load_graph_artifact


def search_graph(session_id: uuid.UUID, query: str, limit: int = 8) -> SearchResponse:
    graph = load_graph_artifact(session_id)
    query_embedding = embed_query(query)
    query_terms = extract_candidate_terms(query, top_k=8) or [query]

    concept_hits: list[SearchConceptHit] = []
    for concept in graph.concepts:
        lexical_bonus = 0.25 if any(term.lower() in concept.name.lower() for term in query_terms) else 0.0
        score = cosine_similarity(query_embedding, concept.embedding) + lexical_bonus
        evidence_chunk_ids = [evidence.chunk_id for evidence in concept.evidence_refs[:3]]
        concept_hits.append(
            SearchConceptHit(
                concept_id=concept.concept_id,
                name=concept.name,
                canonical_name=concept.canonical_name,
                score=round(score, 3),
                source_count=concept.source_count,
                evidence_chunk_ids=evidence_chunk_ids,
            )
        )
    concept_hits.sort(key=lambda item: item.score, reverse=True)

    all_chunks = [chunk for artifact in list_ingest_artifacts(session_id) for chunk in artifact.chunks]
    chunk_hits: list[SearchChunkHit] = []
    for chunk in all_chunks:
        lexical_score = sum(chunk.text.lower().count(term.lower()) for term in query_terms)
        score = cosine_similarity(query_embedding, chunk.embedding) + lexical_score * 0.1
        chunk_hits.append(
            SearchChunkHit(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                source_type=chunk.source_type,
                score=round(score, 3),
                text=best_snippet(chunk.text, query_terms),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                time_start=chunk.time_start,
                time_end=chunk.time_end,
            )
        )
    chunk_hits.sort(key=lambda item: item.score, reverse=True)

    return SearchResponse(
        session_id=session_id,
        query=query,
        concepts=concept_hits[:limit],
        chunks=chunk_hits[:limit],
    )


def get_subgraph(session_id: uuid.UUID, center_concept_id: str, depth: int = 1) -> SubgraphResponse:
    graph = load_graph_artifact(session_id)
    concept_by_id = {concept.concept_id: concept for concept in graph.concepts}
    if center_concept_id not in concept_by_id:
        raise ValueError(f"Concept {center_concept_id} not found")

    queue = deque([(center_concept_id, 0)])
    visited = {center_concept_id}
    nodes = [
        SubgraphNode(
            id=center_concept_id,
            label=concept_by_id[center_concept_id].name,
            node_type="concept",
            metadata={"importance_score": concept_by_id[center_concept_id].importance_score},
        )
    ]
    edges: list[SubgraphEdge] = []

    while queue:
        current, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for edge in graph.edges:
            if edge.source != current or edge.edge_type not in {EdgeType.relates_to, EdgeType.co_occurs_with}:
                continue
            target = edge.target
            if target not in concept_by_id:
                continue
            edges.append(SubgraphEdge(source=edge.source, target=edge.target, edge_type=edge.edge_type, properties=edge.properties))
            if target not in visited:
                visited.add(target)
                queue.append((target, current_depth + 1))
                nodes.append(
                    SubgraphNode(
                        id=target,
                        label=concept_by_id[target].name,
                        node_type="concept",
                        metadata={"importance_score": concept_by_id[target].importance_score},
                    )
                )

    return SubgraphResponse(
        session_id=session_id,
        center_concept_id=center_concept_id,
        nodes=nodes,
        edges=edges,
    )
