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
    session.status = SessionStatus.building_graph
    session.error_message = None
    session.updated_at = datetime.utcnow()
    save_session(session)
    try:
        artifacts = list_ingest_artifacts(session_id)
        if not artifacts:
            raise ValueError("No ingest artifacts found. Run /ingest/pdf or /ingest/audio first.")

        chunks = [chunk for artifact in artifacts for chunk in artifact.chunks]
        if not chunks:
            raise ValueError("No text chunks available. Check the uploaded files and ingest output.")
        if all(_is_asr_failure_chunk(chunk) for chunk in chunks):
            raise RuntimeError(
                "Audio transcription failed before graph extraction. "
                "Install/configure an ASR backend such as openai-whisper or faster-whisper, then re-ingest the audio."
            )

        concepts, edges = _extract_graph_structure(chunks)
        if not concepts:
            raise ValueError("No concepts could be extracted from the ingested sources.")
        _apply_concept_embeddings(concepts)
        _assign_graph_metrics(concepts, edges)
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

    concepts: list[ConceptNode] = []

    for candidate in extracted.concepts:
        aliases = sorted(
            {
                alias
                for alias in [candidate.name, candidate.canonical_name, *candidate.aliases]
                if alias.strip()
            }
        )
        definition = candidate.definition.strip()
        if not definition:
            definition = summarize_text(candidate.summary or candidate.name, max_sentences=1, max_chars=150)
        summary = candidate.summary.strip() or definition

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
                source_count=_matching_source_count(chunks, aliases or [candidate.name]),
                evidence_refs=[],
            )
        )

    return concepts


def _build_edges_from_llm(
    chunks: list[EvidenceChunk],
    concepts: list[ConceptNode],
    extracted: GraphExtractionResult,
) -> list[GraphEdge]:
    concept_by_canonical = {concept.canonical_name: concept for concept in concepts}
    relation_edges: list[GraphEdge] = []
    existing_edge_keys: set[tuple[str, str, EdgeType, str | None]] = set()

    for relation in extracted.relations:
        source = concept_by_canonical.get(canonicalize_term(relation.source_canonical_name))
        target = concept_by_canonical.get(canonicalize_term(relation.target_canonical_name))
        if source is None or target is None or source.concept_id == target.concept_id:
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
                },
            )
            relation_edges.append(edge)
            existing_edge_keys.add(key)
        elif relation.edge_type == EdgeType.co_occurs_with.value:
            key = (source.concept_id, target.concept_id, EdgeType.co_occurs_with, None)
            if key in existing_edge_keys:
                continue
            edge = GraphEdge(
                source=source.concept_id,
                target=target.concept_id,
                edge_type=EdgeType.co_occurs_with,
                properties={
                    "normalized_weight": round(max(relation.confidence, 0.55), 3),
                },
            )
            relation_edges.append(edge)
            existing_edge_keys.add(key)

    return relation_edges


def _matching_source_count(chunks: list[EvidenceChunk], terms: list[str]) -> int:
    lowered_terms = [term.lower() for term in terms if term]
    if not lowered_terms:
        return 0
    source_ids = {
        chunk.source_id
        for chunk in chunks
        if any(term in chunk.text.lower() for term in lowered_terms)
    }
    return len(source_ids)


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
                evidence_refs=[],
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


def _assign_graph_metrics(concepts: list[ConceptNode], edges: list[GraphEdge]) -> None:
    concept_ids = {concept.concept_id for concept in concepts}
    if not concept_ids:
        return

    adjacency: dict[str, set[str]] = {concept_id: set() for concept_id in concept_ids}
    weighted_degrees: dict[str, float] = {concept_id: 0.0 for concept_id in concept_ids}

    for edge in edges:
        if edge.source not in concept_ids or edge.target not in concept_ids:
            continue
        if edge.edge_type == EdgeType.relates_to:
            weight = 1.0 + float(edge.properties.get("confidence", 0.0))
        elif edge.edge_type == EdgeType.co_occurs_with:
            weight = 0.5 + float(edge.properties.get("normalized_weight", 0.0))
        else:
            continue
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
        weighted_degrees[edge.source] += weight
        weighted_degrees[edge.target] += weight

    n = len(concept_ids)
    degree_centrality = {
        concept_id: (len(neighbors) / (n - 1) if n > 1 else 0.0)
        for concept_id, neighbors in adjacency.items()
    }
    max_weighted_degree = max(weighted_degrees.values(), default=0.0)
    weighted_degree_centrality = {
        concept_id: (weighted_degree / max_weighted_degree if max_weighted_degree > 0 else 0.0)
        for concept_id, weighted_degree in weighted_degrees.items()
    }
    betweenness_centrality = _betweenness_centrality(adjacency)
    closeness_centrality = _closeness_centrality(adjacency)

    for concept in concepts:
        concept_id = concept.concept_id
        metrics = {
            "degree_centrality": degree_centrality.get(concept_id, 0.0),
            "weighted_degree_centrality": weighted_degree_centrality.get(concept_id, 0.0),
            "betweenness_centrality": betweenness_centrality.get(concept_id, 0.0),
            "closeness_centrality": closeness_centrality.get(concept_id, 0.0),
        }
        concept.graph_metrics = {key: round(max(0.0, min(1.0, value)), 4) for key, value in metrics.items()}
        concept.importance_score = round(
            max(
                0.0,
                min(
                    1.0,
                    concept.graph_metrics["weighted_degree_centrality"] * 0.45
                    + concept.graph_metrics["betweenness_centrality"] * 0.25
                    + concept.graph_metrics["closeness_centrality"] * 0.20
                    + concept.graph_metrics["degree_centrality"] * 0.10,
                ),
            ),
            4,
        )


def _betweenness_centrality(adjacency: dict[str, set[str]]) -> dict[str, float]:
    nodes = list(adjacency)
    scores = {node: 0.0 for node in nodes}
    if len(nodes) <= 2:
        return scores

    for source in nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node: [] for node in nodes}
        path_counts = dict.fromkeys(nodes, 0.0)
        path_counts[source] = 1.0
        distances = dict.fromkeys(nodes, -1)
        distances[source] = 0
        queue = [source]

        for current in queue:
            stack.append(current)
            for neighbor in adjacency[current]:
                if distances[neighbor] < 0:
                    queue.append(neighbor)
                    distances[neighbor] = distances[current] + 1
                if distances[neighbor] == distances[current] + 1:
                    path_counts[neighbor] += path_counts[current]
                    predecessors[neighbor].append(current)

        dependencies = dict.fromkeys(nodes, 0.0)
        while stack:
            node = stack.pop()
            for predecessor in predecessors[node]:
                if path_counts[node] > 0:
                    share = path_counts[predecessor] / path_counts[node]
                    dependencies[predecessor] += share * (1.0 + dependencies[node])
            if node != source:
                scores[node] += dependencies[node]

    # Undirected graph normalization: divide duplicated paths, then scale to 0..1.
    scale = 1.0 / ((len(nodes) - 1) * (len(nodes) - 2))
    return {node: score * scale for node, score in scores.items()}


def _closeness_centrality(adjacency: dict[str, set[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    n = len(adjacency)
    for source in adjacency:
        distances = {source: 0}
        queue = [source]
        for current in queue:
            for neighbor in adjacency[current]:
                if neighbor in distances:
                    continue
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)

        reachable = len(distances) - 1
        total_distance = sum(distances.values())
        if reachable <= 0 or total_distance <= 0 or n <= 1:
            scores[source] = 0.0
            continue
        scores[source] = (reachable / total_distance) * (reachable / (n - 1))
    return scores


def _is_asr_failure_chunk(chunk: EvidenceChunk) -> bool:
    text = chunk.text.lower()
    return chunk.source_type.value == "audio" and text.startswith("asr failed for ")


def _build_edges(chunks: list[EvidenceChunk], concepts: list[ConceptNode]) -> list[GraphEdge]:
    concept_by_id = {concept.concept_id: concept for concept in concepts}
    concept_terms = {concept.concept_id: set(concept.aliases + [concept.name, concept.canonical_name]) for concept in concepts}

    cooccur_counts: Counter[tuple[str, str]] = Counter()
    relation_counts: Counter[tuple[str, str, RelationType]] = Counter()
    for chunk in chunks:
        mentioned = _mentioned_concepts(chunk, concept_terms)
        for left, right in itertools.combinations(sorted(mentioned), 2):
            cooccur_counts[(left, right)] += 1

        for relation in _extract_relations(chunk.text, mentioned, concept_by_id):
            relation_counts[relation] += 1

    relation_edges: list[GraphEdge] = []
    for (left, right, relation_type), count in relation_counts.items():
        relation_edges.append(
            GraphEdge(
                source=left,
                target=right,
                edge_type=EdgeType.relates_to,
                properties={
                    "relation_type": relation_type.value,
                    "confidence": round(min(0.95, 0.55 + count * 0.1), 2),
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
