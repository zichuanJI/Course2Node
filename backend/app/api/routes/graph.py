from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from app.core.types import BuildGraphRequest, GenerateNotesRequest, IngestRequest, SearchRequest
from app.services.graph_builder import build_graph
from app.services.ingestion import ingest_source
from app.services.notes import generate_notes, get_note
from app.services.search import get_subgraph, search_graph
from app.storage.local import load_graph_artifact

router = APIRouter(tags=["graph"])


@router.post("/ingest/pdf")
async def ingest_pdf(request: IngestRequest):
    try:
        artifact = ingest_source(request.session_id, request.source_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return artifact.model_dump(mode="json")


@router.post("/ingest/audio")
async def ingest_audio(request: IngestRequest):
    try:
        artifact = ingest_source(request.session_id, request.source_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return artifact.model_dump(mode="json")


@router.post("/build_graph")
async def build_graph_endpoint(request: BuildGraphRequest):
    try:
        graph = build_graph(request.session_id)
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
        result = search_graph(request.session_id, request.query, request.limit)
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
        result = get_subgraph(session_id, concept_id, depth)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/generate_notes")
async def generate_notes_endpoint(request: GenerateNotesRequest):
    try:
        note = generate_notes(request)
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


@router.get("/graph/{session_id}")
async def get_graph_endpoint(session_id: uuid.UUID):
    try:
        graph = load_graph_artifact(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph not found.") from exc
    return graph.model_dump(mode="json")
