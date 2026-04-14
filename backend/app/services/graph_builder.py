from __future__ import annotations

import itertools
import uuid
from collections import Counter, defaultdict

from app.core.types import (
    ConceptNode,
    CourseSession,
    EdgeType,
    EvidenceChunk,
    EvidenceRef,
    GraphArtifact,
    GraphEdge,
    RelationType,
    SessionStatus,
    TopicClusterNode,
)
from app.services.text_utils import (
    best_snippet,
    canonicalize_term,
    cosine_similarity,
    extract_candidate_terms,
    hash_embedding,
    summarize_text,
)
from app.storage.local import list_ingest_artifacts, load_session, save_graph_artifact, save_session


def build_graph(session_id: uuid.UUID) -> GraphArtifact:
    session = load_session(session_id)
    artifacts = list_ingest_artifacts(session_id)
    chunks = [chunk for artifact in artifacts for chunk in artifact.chunks]

    concepts = _build_concepts(chunks)
    edges = _build_edges(chunks, concepts)
    _assign_importance_scores(concepts, edges)
    clusters = _build_clusters(concepts, edges)
    graph = GraphArtifact(
        session_id=session_id,
        concepts=concepts,
        topic_clusters=clusters,
        edges=edges,
    )
    save_graph_artifact(graph)

    session.status = SessionStatus.graph_ready
    session.stats.document_count = sum(1 for source in session.source_files if source.kind.value == "pdf")
    session.stats.audio_count = sum(1 for source in session.source_files if source.kind.value == "audio")
    session.stats.chunk_count = len(chunks)
    session.stats.concept_count = len(concepts)
    session.stats.relation_count = len(edges)
    session.stats.cluster_count = len(clusters)
    save_session(session)
    return graph


def _build_concepts(chunks: list[EvidenceChunk]) -> list[ConceptNode]:
    term_chunk_hits: dict[str, list[EvidenceChunk]] = defaultdict(list)
    alias_map: dict[str, set[str]] = defaultdict(set)
    source_map: dict[str, set[str]] = defaultdict(set)

    for chunk in chunks:
        raw_terms = extract_candidate_terms(chunk.text, top_k=10)
        if not raw_terms:
            raw_terms = chunk.keywords[:8]
        seen_terms: set[str] = set()
        for raw_term in raw_terms:
            canonical = canonicalize_term(raw_term)
            if not canonical or canonical in seen_terms:
                continue
            seen_terms.add(canonical)
            term_chunk_hits[canonical].append(chunk)
            alias_map[canonical].add(raw_term)
            source_map[canonical].add(chunk.source_id)

    ranked_terms = sorted(
        term_chunk_hits.items(),
        key=lambda item: (len(item[1]), sum(len(chunk.text) for chunk in item[1])),
        reverse=True,
    )

    concepts: list[ConceptNode] = []
    for canonical, hits in ranked_terms[:60]:
        unique_chunk_ids = {chunk.chunk_id for chunk in hits}
        if len(unique_chunk_ids) < 2 and len(chunks) > 3:
            continue
        name = sorted(alias_map[canonical], key=len, reverse=True)[0]
        snippet = best_snippet(" ".join(chunk.text for chunk in hits[:3]), [name])
        concepts.append(
            ConceptNode(
                concept_id=f"concept:{canonical}",
                name=name,
                canonical_name=canonical,
                aliases=sorted(alias_map[canonical]),
                definition=summarize_text(snippet, max_sentences=1, max_chars=150),
                embedding=hash_embedding(" ".join(chunk.text for chunk in hits[:4])),
                importance_score=0.0,
                source_count=len(source_map[canonical]),
                evidence_refs=[
                    _chunk_to_ref(chunk, canonical)
                    for chunk in hits[:6]
                ],
            )
        )

    return concepts


def _assign_importance_scores(concepts: list[ConceptNode], edges: list[GraphEdge]) -> None:
    concept_ids = {concept.concept_id for concept in concepts}
    degrees: dict[str, float] = {concept_id: 0.0 for concept_id in concept_ids}

    for edge in edges:
        if edge.source not in concept_ids or edge.target not in concept_ids:
            continue
        if edge.edge_type == EdgeType.relates_to:
            weight = 1.0 + float(edge.properties.get("confidence", 0.0))
        elif edge.edge_type == EdgeType.co_occurs_with:
            weight = 0.5 + float(edge.properties.get("normalized_weight", 0.0))
        else:
            continue
        degrees[edge.source] += weight
        degrees[edge.target] += weight

    max_degree = max(degrees.values(), default=0.0)
    if max_degree <= 0:
        return

    for concept in concepts:
        concept.importance_score = round(degrees[concept.concept_id] / max_degree, 4)


def _chunk_to_ref(chunk: EvidenceChunk, term: str) -> EvidenceRef:
    if chunk.source_type.value == "pdf":
        locator = f"p.{chunk.page_start}"
    else:
        locator = f"{_format_seconds(chunk.time_start)}-{_format_seconds(chunk.time_end)}"
    return EvidenceRef(
        chunk_id=chunk.chunk_id,
        source_id=chunk.source_id,
        source_type=chunk.source_type,
        locator=locator,
        snippet=best_snippet(chunk.text, [term]),
    )


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "00:00"
    minutes = int(value // 60)
    seconds = int(value % 60)
    return f"{minutes:02d}:{seconds:02d}"


def _build_edges(chunks: list[EvidenceChunk], concepts: list[ConceptNode]) -> list[GraphEdge]:
    concept_by_id = {concept.concept_id: concept for concept in concepts}
    concept_terms = {concept.concept_id: set(concept.aliases + [concept.name, concept.canonical_name]) for concept in concepts}

    cooccur_counts: Counter[tuple[str, str]] = Counter()
    evidence_counts: Counter[tuple[str, str, RelationType]] = Counter()
    for chunk in chunks:
        mentioned = _mentioned_concepts(chunk, concept_terms)
        for left, right in itertools.combinations(sorted(mentioned), 2):
            cooccur_counts[(left, right)] += 1

        for relation in _extract_relations(chunk.text, mentioned, concept_by_id):
            evidence_counts[relation] += 1

    relation_edges: list[GraphEdge] = []
    for (left, right, relation_type), count in evidence_counts.items():
        relation_edges.append(
            GraphEdge(
                source=left,
                target=right,
                edge_type=EdgeType.relates_to,
                properties={
                    "relation_type": relation_type.value,
                    "confidence": round(min(0.95, 0.55 + count * 0.1), 2),
                    "evidence_count": count,
                },
            )
        )

    for (left, right), count in cooccur_counts.items():
        if count < 2 and not _is_semantically_close(concept_by_id[left], concept_by_id[right]):
            continue
        normalized = round(
            count / max(1.0, concept_by_id[left].importance_score + concept_by_id[right].importance_score),
            3,
        )
        relation_edges.append(
            GraphEdge(
                source=left,
                target=right,
                edge_type=EdgeType.co_occurs_with,
                properties={
                    "cooccur_count": count,
                    "doc_count": min(concept_by_id[left].source_count, concept_by_id[right].source_count),
                    "normalized_weight": normalized,
                },
            )
        )
        if not any(
            edge.source == left and edge.target == right and edge.edge_type == EdgeType.relates_to
            for edge in relation_edges
        ):
            relation_edges.append(
                GraphEdge(
                    source=left,
                    target=right,
                    edge_type=EdgeType.relates_to,
                    properties={
                        "relation_type": RelationType.similar_to.value,
                        "confidence": round(0.45 + min(0.4, count * 0.08), 2),
                        "evidence_count": count,
                    },
                )
            )

    return relation_edges


def _mentioned_concepts(
    chunk: EvidenceChunk,
    concept_terms: dict[str, set[str]],
) -> set[str]:
    lowered = chunk.text.lower()
    mentioned: set[str] = set()
    for concept_id, terms in concept_terms.items():
        if any(term and term.lower() in lowered for term in terms):
            mentioned.add(concept_id)
    return mentioned


def _extract_relations(
    text: str,
    mentioned: set[str],
    concept_by_id: dict[str, ConceptNode],
) -> list[tuple[str, str, RelationType]]:
    if len(mentioned) < 2:
        return []
    ordered = sorted(
        mentioned,
        key=lambda concept_id: text.lower().find(concept_by_id[concept_id].name.lower()),
    )
    results: list[tuple[str, str, RelationType]] = []
    rules = [
        (RelationType.is_a, ("属于", "是一种", "type of", "is a")),
        (RelationType.part_of, ("组成", "包括", "part of", "consists of")),
        (RelationType.prerequisite_of, ("前提", "基础", "依赖", "depends on", "requires")),
        (RelationType.causes, ("导致", "造成", "引起", "leads to", "causes")),
        (RelationType.used_for, ("用于", "用来", "用于解决", "used for", "applied to")),
    ]

    lowered = text.lower()
    for relation_type, cues in rules:
        if not any(cue in lowered for cue in cues):
            continue
        if len(ordered) >= 2:
            results.append((ordered[0], ordered[1], relation_type))
    return results


def _is_semantically_close(left: ConceptNode, right: ConceptNode) -> bool:
    return cosine_similarity(left.embedding, right.embedding) > 0.48


def _build_clusters(
    concepts: list[ConceptNode],
    edges: list[GraphEdge],
) -> list[TopicClusterNode]:
    concept_ids = {concept.concept_id for concept in concepts}
    adjacency: dict[str, set[str]] = {concept_id: set() for concept_id in concept_ids}
    for edge in edges:
        if edge.source not in concept_ids or edge.target not in concept_ids:
            continue
        if edge.edge_type not in {EdgeType.relates_to, EdgeType.co_occurs_with}:
            continue
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    clusters: list[list[str]] = []
    seen: set[str] = set()
    for concept_id in concept_ids:
        if concept_id in seen:
            continue
        stack = [concept_id]
        component: list[str] = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(adjacency[current] - seen)
        clusters.append(component)

    cluster_nodes: list[TopicClusterNode] = []
    for index, cluster_concepts in enumerate(sorted(clusters, key=len, reverse=True), start=1):
        sorted_concepts = sorted(
            (next(concept for concept in concepts if concept.concept_id == concept_id) for concept_id in cluster_concepts),
            key=lambda concept: concept.importance_score,
            reverse=True,
        )
        top_names = [concept.name for concept in sorted_concepts[:3]]
        title = " / ".join(top_names) if top_names else f"Topic {index}"
        summary = f"围绕 {', '.join(top_names)} 的知识点簇。" if top_names else "自动聚类主题。"
        cluster_id = f"cluster:{index}"
        cluster_nodes.append(
            TopicClusterNode(
                cluster_id=cluster_id,
                title=title,
                summary=summary,
                concept_ids=[concept.concept_id for concept in sorted_concepts],
            )
        )

    return cluster_nodes
