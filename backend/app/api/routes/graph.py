from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.core.types import BuildGraphRequest, GenerateExamRequest, GenerateNotesRequest, IngestRequest, SearchRequest
from app.services.exam import generate_exam, get_exam
from app.services.graph_builder import build_graph
from app.services.ingestion import ingest_source
from app.services.notes import generate_notes, get_note
from app.services.search import get_subgraph, search_graph
from app.storage.local import load_graph_artifact

router = APIRouter(tags=["graph"])


@router.post("/ingest/pdf")
async def ingest_pdf(request: IngestRequest):
    try:
        artifact = await run_in_threadpool(ingest_source, request.session_id, request.source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return artifact.model_dump(mode="json")


@router.post("/ingest/audio")
async def ingest_audio(request: IngestRequest):
    try:
        artifact = await run_in_threadpool(ingest_source, request.session_id, request.source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return artifact.model_dump(mode="json")


@router.post("/build_graph")
async def build_graph_endpoint(request: BuildGraphRequest):
    try:
        graph = await run_in_threadpool(build_graph, request.session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc
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


@router.post("/search")
async def search_endpoint(request: SearchRequest):
    try:
        result = await run_in_threadpool(search_graph, request.session_id, request.query, request.limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph not found.") from exc
    return result.model_dump(mode="json")


@router.get("/graph/subgraph")
async def subgraph_endpoint(
    session_id: uuid.UUID = Query(...),
    concept_id: str = Query(...),
    depth: int = Query(1, ge=1, le=3),
):
    try:
        result = await run_in_threadpool(get_subgraph, session_id, concept_id, depth)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/generate_notes")
async def generate_notes_endpoint(request: GenerateNotesRequest):
    try:
        note = await run_in_threadpool(generate_notes, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph or session not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return note.model_dump(mode="json")


@router.get("/notes/{session_id}")
async def get_note_endpoint(session_id: uuid.UUID):
    try:
        note = get_note(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Note not found.") from exc
    return note.model_dump(mode="json")


@router.post("/generate_exam")
async def generate_exam_endpoint(request: GenerateExamRequest):
    try:
        exam = await run_in_threadpool(generate_exam, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph or session not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return exam.model_dump(mode="json")


@router.get("/exam/{session_id}")
async def get_exam_endpoint(session_id: uuid.UUID):
    try:
        exam = get_exam(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Exam not found.") from exc
    return exam.model_dump(mode="json")


@router.get("/graph/{session_id}")
async def get_graph_endpoint(session_id: uuid.UUID):
    try:
        graph = load_graph_artifact(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph not found.") from exc
    return graph.model_dump(mode="json")
