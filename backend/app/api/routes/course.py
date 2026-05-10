"""Course-level API routes for aggregate graph and notes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.types import BuildCourseGraphRequest
from app.services.course_graph_builder import build_course_graph
from app.storage.local import find_course_session, load_graph_artifact

router = APIRouter(prefix="/course", tags=["course"])


@router.post("/build_graph")
async def build_course_graph_endpoint(request: BuildCourseGraphRequest):
    try:
        graph = await run_in_threadpool(
            build_course_graph, request.course_title, request.top_n_core,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": str(graph.session_id),
        "concept_count": len(graph.concepts),
        "edge_count": len(graph.edges),
        "cluster_count": len(graph.topic_clusters),
    }


@router.get("/session/{course_title}")
async def get_course_session_endpoint(course_title: str):
    session = find_course_session(course_title)
    if session is None:
        raise HTTPException(status_code=404, detail="Course graph session not found.")
    return session.model_dump(mode="json")


@router.get("/graph/{course_title}")
async def get_course_graph_endpoint(course_title: str):
    session = find_course_session(course_title)
    if session is None:
        raise HTTPException(status_code=404, detail="Course graph not found.")
    try:
        graph = load_graph_artifact(session.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Course graph artifact not found.") from exc
    return graph.model_dump(mode="json")
