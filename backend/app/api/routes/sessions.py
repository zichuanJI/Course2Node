from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.storage.local import list_session_ids, load_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
async def list_sessions():
    sessions = []
    for session_id in list_session_ids():
        try:
            session = load_session(session_id)
        except FileNotFoundError:
            continue
        sessions.append(session.model_dump(mode="json"))
    return sessions


@router.get("/{session_id}")
async def get_session(session_id: uuid.UUID):
    try:
        session = load_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return session.model_dump(mode="json")


@router.get("/{session_id}/status")
async def get_session_status(session_id: uuid.UUID):
    try:
        session = load_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return {
        "session_id": str(session.session_id),
        "status": session.status,
        "stats": session.stats.model_dump(),
        "error_message": session.error_message,
    }

