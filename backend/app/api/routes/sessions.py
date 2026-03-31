"""LectureSession CRUD endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LectureSessionORM
from app.db.session import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LectureSessionORM).order_by(LectureSessionORM.created_at.desc()))
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "course_title": s.course_title,
            "lecture_title": s.lecture_title,
            "status": s.status,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@router.get("/{session_id}")
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(LectureSessionORM, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": str(session.id),
        "course_title": session.course_title,
        "lecture_title": session.lecture_title,
        "language": session.language,
        "status": session.status,
        "source_files": session.source_files,
        "error_message": session.error_message,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


@router.get("/{session_id}/status")
async def get_session_status(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(LectureSessionORM, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": str(session.id), "status": session.status}
