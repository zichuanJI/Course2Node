"""Course-level graph builder — merges per-lecture graphs into one aggregate graph."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.core.types import (
    ConceptNode,
    CourseGraphMeta,
    CourseSession,
    EdgeType,
    GraphArtifact,
    GraphEdge,
    SessionStats,
    SessionStatus,
    TopicClusterNode,
)
from app.services.graph_builder import (
    _apply_concept_embeddings,
    _assign_graph_metrics,
    _build_clusters,
)
from app.services.text_utils import cosine_similarity
from app.storage.local import (
    COURSE_GRAPH_LECTURE_PREFIX,
    find_course_session,
    list_sessions_by_course,
    load_graph_artifact,
    save_graph_artifact,
    save_session,
)

logger = logging.getLogger(__name__)


def build_course_graph(course_title: str, top_n_core: int = 15, top_n_per_session: int = 6) -> GraphArtifact:
    """Merge all per-lecture graphs for *course_title* into a single course graph.

    Args:
        course_title: The course to merge.
        top_n_core: Number of core concepts in the final hierarchy.
        top_n_per_session: Only keep the top-N concepts (by importance_score)
            from each sub-graph before merging, to avoid an overcrowded total graph.
    """

    # ── 1. Locate or create virtual session ──────────────────────────────
    virtual = find_course_session(course_title)
    if virtual is None:
        virtual = CourseSession(
            session_id=uuid.uuid4(),
            course_title=course_title,
            lecture_title=f"{COURSE_GRAPH_LECTURE_PREFIX}{course_title}",
            status=SessionStatus.merging_graph,
        )
    else:
        virtual.status = SessionStatus.merging_graph
        virtual.error_message = None
    virtual.updated_at = datetime.utcnow()
    save_session(virtual)

    try:
        return _do_merge(virtual, course_title, top_n_core, top_n_per_session)
    except Exception as exc:
        virtual.status = SessionStatus.failed
        virtual.error_message = str(exc)
        virtual.updated_at = datetime.utcnow()
        save_session(virtual)
        raise


def _do_merge(virtual: CourseSession, course_title: str, top_n_core: int, top_n_per_session: int) -> GraphArtifact:
    # ── 2. Collect sub-graphs ────────────────────────────────────────────
    sessions = list_sessions_by_course(course_title)
    ready = [
        s for s in sessions
        if s.status in {SessionStatus.graph_ready, SessionStatus.notes_ready}
    ]
    if not ready:
        raise ValueError(f"课程「{course_title}」下没有已构建图谱的讲次。")

    sub_graphs: list[GraphArtifact] = []
    source_session_ids: list[str] = []
    for s in ready:
        try:
            graph = load_graph_artifact(s.session_id)
            sub_graphs.append(graph)
            source_session_ids.append(str(s.session_id))
        except FileNotFoundError:
            logger.warning("Graph artifact missing for session %s, skipping.", s.session_id)

    if not sub_graphs:
        raise ValueError("所有子图谱文件缺失，无法合并。")

    # ── 2b. Keep only top-N concepts per sub-graph ───────────────────────
    sub_graphs = _trim_subgraphs(sub_graphs, top_n_per_session)

    # ── 3. Merge concepts ────────────────────────────────────────────────
    merged_concepts = _merge_concepts(sub_graphs)
    if not merged_concepts:
        raise ValueError("合并后没有有效概念。")

    # ── 4. Merge edges ───────────────────────────────────────────────────
    merged_edges = _merge_edges(sub_graphs, merged_concepts)

    # ── 5. Re-compute embeddings ─────────────────────────────────────────
    _apply_concept_embeddings(merged_concepts)

    # ── 5b. Add cross-chapter semantic edges ─────────────────────────────
    merged_edges = _add_cross_cluster_edges(merged_concepts, merged_edges)

    # ── 6. Re-compute graph metrics ──────────────────────────────────────
    _assign_graph_metrics(merged_concepts, merged_edges)

    # ── 7. Re-cluster ────────────────────────────────────────────────────
    clusters = _build_clusters(merged_concepts, merged_edges)

    # ── 8. Build hierarchy ───────────────────────────────────────────────
    course_meta = _build_hierarchy(merged_concepts, clusters, top_n_core, source_session_ids)

    # ── 9. Save ──────────────────────────────────────────────────────────
    graph = GraphArtifact(
        session_id=virtual.session_id,
        concepts=merged_concepts,
        topic_clusters=clusters,
        edges=merged_edges,
        course_meta=course_meta,
    )
    save_graph_artifact(graph)

    virtual.status = SessionStatus.graph_ready
    virtual.error_message = None
    virtual.stats = SessionStats(
        concept_count=len(merged_concepts),
        relation_count=len(merged_edges),
        cluster_count=len(clusters),
        document_count=len(sub_graphs),
    )
    virtual.updated_at = graph.built_at
    save_session(virtual)
    return graph


# ── Merge helpers ────────────────────────────────────────────────────────────


def _trim_subgraphs(sub_graphs: list[GraphArtifact], top_n: int) -> list[GraphArtifact]:
    """Keep only the top-N concepts (by importance_score) from each sub-graph.

    Edges are filtered to only retain those between the kept concepts.
    This reduces the total number of nodes in the aggregate graph and avoids clutter.
    """
    trimmed: list[GraphArtifact] = []
    for graph in sub_graphs:
        if len(graph.concepts) <= top_n:
            trimmed.append(graph)
            continue

        # Sort by importance_score descending, take top-N
        sorted_concepts = sorted(graph.concepts, key=lambda c: c.importance_score, reverse=True)
        kept_concepts = sorted_concepts[:top_n]
        kept_ids = {c.concept_id for c in kept_concepts}

        # Filter edges to only those between kept concepts
        kept_edges = [
            e for e in graph.edges
            if e.source in kept_ids and e.target in kept_ids
        ]

        trimmed.append(graph.model_copy(update={
            "concepts": kept_concepts,
            "edges": kept_edges,
        }))
        logger.info(
            "Trimmed sub-graph %s: %d -> %d concepts, %d -> %d edges",
            graph.session_id,
            len(graph.concepts), len(kept_concepts),
            len(graph.edges), len(kept_edges),
        )

    return trimmed


def _merge_concepts(sub_graphs: list[GraphArtifact]) -> list[ConceptNode]:
    """De-duplicate concepts across sub-graphs by canonical_name, merging info."""
    concept_map: dict[str, ConceptNode] = {}

    for graph in sub_graphs:
        for concept in graph.concepts:
            existing = concept_map.get(concept.canonical_name)
            if existing is None:
                # Clone the concept (reset embedding so it gets recomputed)
                concept_map[concept.canonical_name] = concept.model_copy(
                    update={"embedding": [], "importance_score": 0.0, "graph_metrics": {}}
                )
                continue

            # Merge info into existing
            if len(concept.definition) > len(existing.definition):
                existing.definition = concept.definition
            if len(concept.summary) > len(existing.summary):
                existing.summary = concept.summary
            if len(concept.name) > len(existing.name):
                existing.name = concept.name

            # Merge aliases
            merged_aliases = sorted(set(existing.aliases) | set(concept.aliases))
            existing.aliases = merged_aliases[:12]

            # Merge key_points (deduplicate)
            seen_kp = {kp.lower() for kp in existing.key_points}
            for kp in concept.key_points:
                if kp.lower() not in seen_kp:
                    existing.key_points.append(kp)
                    seen_kp.add(kp.lower())
            existing.key_points = existing.key_points[:6]

            # Merge tags
            merged_tags = sorted(set(existing.tags) | set(concept.tags))
            existing.tags = merged_tags[:6]

            # Merge prerequisites and applications
            existing.prerequisites = sorted(set(existing.prerequisites) | set(concept.prerequisites))[:6]
            existing.applications = sorted(set(existing.applications) | set(concept.applications))[:6]

            # Take max source count
            existing.source_count = max(existing.source_count, concept.source_count)

    return list(concept_map.values())


def _merge_edges(sub_graphs: list[GraphArtifact], merged_concepts: list[ConceptNode]) -> list[GraphEdge]:
    """De-duplicate edges by (source, target, edge_type, relation_type), taking max confidence."""
    valid_ids = {c.concept_id for c in merged_concepts}
    edge_map: dict[tuple[str, str, str, str | None], GraphEdge] = {}

    for graph in sub_graphs:
        for edge in graph.edges:
            if edge.source not in valid_ids or edge.target not in valid_ids:
                continue
            if edge.source == edge.target:
                continue

            relation_type = edge.properties.get("relation_type") if edge.edge_type == EdgeType.relates_to else None
            key = (edge.source, edge.target, edge.edge_type.value if isinstance(edge.edge_type, EdgeType) else edge.edge_type, relation_type)

            existing = edge_map.get(key)
            if existing is None:
                edge_map[key] = edge.model_copy()
            else:
                # Take max confidence / weight
                for prop_key in ("confidence", "normalized_weight"):
                    old_val = float(existing.properties.get(prop_key, 0))
                    new_val = float(edge.properties.get(prop_key, 0))
                    if new_val > old_val:
                        existing.properties[prop_key] = round(new_val, 3)

    return list(edge_map.values())


def _add_cross_cluster_edges(
    concepts: list[ConceptNode],
    existing_edges: list[GraphEdge],
    similarity_threshold: float = 0.55,
    max_new_edges: int = 40,
) -> list[GraphEdge]:
    """Bridge disconnected chapter clusters by adding edges based on embedding similarity.

    Each sub-graph is built independently, so cross-chapter relations are never
    generated by the LLM.  After embeddings are computed for the merged graph we
    compare every concept pair that has no existing edge and add a RELATES_TO
    edge when cosine similarity exceeds *similarity_threshold*.
    """
    existing_pairs: set[tuple[str, str]] = set()
    for edge in existing_edges:
        existing_pairs.add((edge.source, edge.target))
        existing_pairs.add((edge.target, edge.source))

    with_embedding = [c for c in concepts if c.embedding and len(c.embedding) > 1]
    if len(with_embedding) < 2:
        return existing_edges

    candidates: list[tuple[float, str, str]] = []
    for i, c1 in enumerate(with_embedding):
        for c2 in with_embedding[i + 1:]:
            if (c1.concept_id, c2.concept_id) in existing_pairs:
                continue
            sim = cosine_similarity(c1.embedding, c2.embedding)
            if sim >= similarity_threshold:
                candidates.append((sim, c1.concept_id, c2.concept_id))

    candidates.sort(reverse=True)
    new_edges = list(existing_edges)
    added = 0
    for sim, src, tgt in candidates:
        if added >= max_new_edges:
            break
        new_edges.append(GraphEdge(
            source=src,
            target=tgt,
            edge_type=EdgeType.relates_to,
            properties={
                "relation_type": "semantic_similarity",
                "confidence": round(sim, 3),
            },
        ))
        added += 1

    if added:
        logger.info("Added %d cross-cluster semantic edges (threshold=%.2f).", added, similarity_threshold)
    return new_edges


def _build_hierarchy(
    concepts: list[ConceptNode],
    clusters: list[TopicClusterNode],
    top_n: int,
    source_session_ids: list[str],
) -> CourseGraphMeta:
    """Select top-N core concepts and assign remaining concepts as children."""
    sorted_concepts = sorted(concepts, key=lambda c: c.importance_score, reverse=True)
    core = sorted_concepts[:top_n]
    core_ids = {c.concept_id for c in core}
    remaining = [c for c in concepts if c.concept_id not in core_ids]

    # Build cluster membership lookup
    cluster_for_concept: dict[str, str] = {}
    for cluster in clusters:
        for concept_id in cluster.concept_ids:
            cluster_for_concept[concept_id] = cluster.cluster_id

    # Assign each remaining concept to the nearest core concept via shared cluster
    children_map: dict[str, list[str]] = {c.concept_id: [] for c in core}

    for concept in remaining:
        cluster_id = cluster_for_concept.get(concept.concept_id)
        assigned = False
        if cluster_id:
            # Find a core concept in the same cluster
            for core_concept in core:
                if cluster_for_concept.get(core_concept.concept_id) == cluster_id:
                    children_map[core_concept.concept_id].append(concept.concept_id)
                    assigned = True
                    break
        if not assigned:
            # Assign to the most important core concept as fallback
            if core:
                children_map[core[0].concept_id].append(concept.concept_id)

    return CourseGraphMeta(
        core_concept_ids=[c.concept_id for c in core],
        children_map=children_map,
        source_session_ids=source_session_ids,
    )
