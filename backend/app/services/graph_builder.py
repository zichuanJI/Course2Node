from __future__ import annotations

import itertools
import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime

from app.config import settings
from app.core.types import (
    ConceptNode,
    EdgeType,
    EvidenceChunk,
    EvidenceRef,
    GraphArtifact,
    GraphEdge,
    RelationType,
    SessionStatus,
    TopicClusterNode,
)
from app.services.embeddings import embed_texts, embedding_configured
from app.services.llm_graph import GraphExtractionResult, extract_graph_candidates, llm_graph_configured
from app.services.text_utils import (
    best_snippet,
    canonicalize_term,
    cosine_similarity,
    extract_candidate_terms,
    hash_embedding,
    summarize_text,
)
from app.storage.local import list_ingest_artifacts, load_session, save_graph_artifact, save_session

logger = logging.getLogger(__name__)


def build_graph(session_id: uuid.UUID) -> GraphArtifact:
    session = load_session(session_id)
    try:
        artifacts = list_ingest_artifacts(session_id)
        if not artifacts:
            raise ValueError("No ingest artifacts found. Run /ingest/pdf or /ingest/audio first.")

        chunks = [chunk for artifact in artifacts for chunk in artifact.chunks]
        if not chunks:
            raise ValueError("No evidence chunks available. Check the uploaded files and ingest output.")

        concepts, edges = _extract_graph_structure(chunks)
        if not concepts:
            raise ValueError("No concepts could be extracted from the ingested sources.")
        _apply_concept_embeddings(concepts)
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
        session.error_message = None
        session.stats.document_count = sum(1 for source in session.source_files if source.kind.value == "pdf")
        session.stats.audio_count = sum(1 for source in session.source_files if source.kind.value == "audio")
        session.stats.chunk_count = len(chunks)
        session.stats.concept_count = len(concepts)
        session.stats.relation_count = len(edges)
        session.stats.cluster_count = len(clusters)
        session.updated_at = graph.built_at
        save_session(session)
        return graph
    except Exception as exc:
        session.status = SessionStatus.failed
        session.error_message = str(exc)
        session.updated_at = datetime.utcnow()
        save_session(session)
        raise


def _extract_graph_structure(chunks: list[EvidenceChunk]) -> tuple[list[ConceptNode], list[GraphEdge]]:
    if llm_graph_configured():
        try:
            extracted = extract_graph_candidates(chunks)
            concepts = _build_concepts_from_llm(chunks, extracted)
            if concepts:
                return concepts, _build_edges_from_llm(chunks, concepts, extracted)
            if settings.graph_llm_strict:
                raise RuntimeError("LLM graph extraction returned no valid concepts after cleaning.")
            logger.warning("LLM graph extraction returned no valid concepts, falling back to rules.")
        except Exception as exc:
            logger.exception("LLM graph extraction failed.")
            if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
                logger.warning("LLM graph extraction timed out, falling back to rule-based extraction.")
                concepts = _build_concepts(chunks)
                return concepts, _build_edges(chunks, concepts)
            if settings.graph_llm_strict:
                raise RuntimeError(f"LLM graph extraction failed: {exc}") from exc
            logger.warning("Falling back to rule-based graph extraction after LLM failure.")

    concepts = _build_concepts(chunks)
    return concepts, _build_edges(chunks, concepts)


def _build_concepts_from_llm(
    chunks: list[EvidenceChunk],
    extracted: GraphExtractionResult,
) -> list[ConceptNode]:
    if not extracted.concepts:
        return []

    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    concepts: list[ConceptNode] = []

    for candidate in extracted.concepts:
        aliases = sorted(
            {
                alias
                for alias in [candidate.name, candidate.canonical_name, *candidate.aliases]
                if alias.strip()
            }
        )
        evidence_refs = _resolve_candidate_evidence_refs(
            chunk_by_id=chunk_by_id,
            evidence_chunk_ids=candidate.evidence_chunk_ids,
            lookup_terms=aliases or [candidate.name],
            term=candidate.canonical_name or candidate.name,
        )
        if not evidence_refs:
            continue

        definition = candidate.definition.strip()
        if not definition:
            snippets = " ".join(ref.snippet for ref in evidence_refs)
            definition = summarize_text(snippets, max_sentences=1, max_chars=150)
        summary = candidate.summary.strip() or summarize_text(
            " ".join(ref.snippet for ref in evidence_refs),
            max_sentences=2,
            max_chars=220,
        )

        source_count = len({ref.source_id for ref in evidence_refs})
        canonical_name = canonicalize_term(candidate.canonical_name or candidate.name)
        concepts.append(
            ConceptNode(
                concept_id=f"concept:{canonical_name}",
                name=candidate.name,
                canonical_name=canonical_name,
                aliases=aliases[:10],
                definition=definition,
                summary=summary,
                key_points=candidate.key_points[:4],
                tags=candidate.tags[:5],
                prerequisites=candidate.prerequisites[:4],
                applications=candidate.applications[:4],
                embedding=[],
                importance_score=0.0,
                source_count=source_count,
                evidence_refs=evidence_refs[:6],
            )
        )

    return concepts


def _build_edges_from_llm(
    chunks: list[EvidenceChunk],
    concepts: list[ConceptNode],
    extracted: GraphExtractionResult,
) -> list[GraphEdge]:
    concept_by_canonical = {concept.canonical_name: concept for concept in concepts}
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    relation_edges: list[GraphEdge] = []
    existing_edge_keys: set[tuple[str, str, EdgeType, str | None]] = set()

    for relation in extracted.relations:
        source = concept_by_canonical.get(canonicalize_term(relation.source_canonical_name))
        target = concept_by_canonical.get(canonicalize_term(relation.target_canonical_name))
        if source is None or target is None or source.concept_id == target.concept_id:
            continue
        valid_evidence_ids = [
            chunk_id
            for chunk_id in dict.fromkeys(relation.evidence_chunk_ids)
            if chunk_id in chunk_by_id
        ]
        if not valid_evidence_ids:
            continue

        if relation.edge_type == EdgeType.relates_to.value and relation.relation_type:
            relation_type = RelationType(relation.relation_type)
            key = (source.concept_id, target.concept_id, EdgeType.relates_to, relation_type.value)
            if key in existing_edge_keys:
                continue
            edge = GraphEdge(
                source=source.concept_id,
                target=target.concept_id,
                edge_type=EdgeType.relates_to,
                properties={
                    "relation_type": relation_type.value,
                    "confidence": round(max(relation.confidence, 0.55), 2),
                    "evidence_count": len(valid_evidence_ids),
                    "evidence_chunk_ids": valid_evidence_ids[:4],
                },
            )
            relation_edges.append(edge)
            existing_edge_keys.add(key)
        elif relation.edge_type == EdgeType.co_occurs_with.value and len(valid_evidence_ids) >= 2:
            key = (source.concept_id, target.concept_id, EdgeType.co_occurs_with, None)
            if key in existing_edge_keys:
                continue
            cooccur_count = len(valid_evidence_ids)
            edge = GraphEdge(
                source=source.concept_id,
                target=target.concept_id,
                edge_type=EdgeType.co_occurs_with,
                properties={
                    "cooccur_count": cooccur_count,
                    "doc_count": min(source.source_count, target.source_count),
                    "normalized_weight": round(min(1.0, 0.25 + cooccur_count * 0.15), 3),
                    "evidence_chunk_ids": valid_evidence_ids[:4],
                },
            )
            relation_edges.append(edge)
            existing_edge_keys.add(key)

    return relation_edges


def _resolve_candidate_evidence_refs(
    *,
    chunk_by_id: dict[str, EvidenceChunk],
    evidence_chunk_ids: list[str],
    lookup_terms: list[str],
    term: str,
) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    seen: set[str] = set()

    for chunk_id in evidence_chunk_ids:
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None or chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        refs.append(_chunk_to_ref(chunk, term))

    if refs:
        return refs

    lowered_terms = [item.lower() for item in lookup_terms if item]
    for chunk in chunk_by_id.values():
        text = chunk.text.lower()
        if not any(alias in text for alias in lowered_terms):
            continue
        refs.append(_chunk_to_ref(chunk, term))
        if len(refs) >= 4:
            break

    return refs


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
                summary=summarize_text(" ".join(chunk.text for chunk in hits[:2]), max_sentences=2, max_chars=220),
                key_points=[
                    summarize_text(chunk.text, max_sentences=1, max_chars=120)
                    for chunk in hits[:3]
                    if summarize_text(chunk.text, max_sentences=1, max_chars=120)
                ][:4],
                tags=sorted(alias_map[canonical])[:5],
                prerequisites=[],
                applications=[],
                embedding=[],
                importance_score=0.0,
                source_count=len(source_map[canonical]),
                evidence_refs=[
                    _chunk_to_ref(chunk, canonical)
                    for chunk in hits[:6]
                ],
            )
        )

    return concepts


def _apply_concept_embeddings(concepts: list[ConceptNode]) -> None:
    if not concepts:
        return
    if not embedding_configured():
        raise RuntimeError("Embedding service is not configured. Set EMBEDDING_API_KEY and EMBEDDING_MODEL.")
    texts = [
        " | ".join(
            part
            for part in [
                concept.name,
                concept.definition,
                concept.summary,
                " ; ".join(concept.key_points),
                " ; ".join(concept.tags),
            ]
            if part
        )
        for concept in concepts
    ]
    vectors = embed_texts(texts)
    if len(vectors) != len(concepts):
        raise RuntimeError("Embedding service returned an unexpected number of concept vectors.")
    for concept, vector in zip(concepts, vectors):
        concept.embedding = vector


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
        locator = f"p.{chunk.page_start}" if chunk.page_start is not None else "PDF"
    else:
        locator = f"{_format_seconds(chunk.time_start)}-{_format_seconds(chunk.time_end)}"
    return EvidenceRef(
        chunk_id=chunk.chunk_id,
        source_id=chunk.source_id,
        source_type=chunk.source_type,
        locator=locator,
        snippet=best_snippet(chunk.text, [term]) if chunk.page_start is not None or chunk.source_type.value != "pdf" else "",
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
