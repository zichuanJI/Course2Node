"""Review events endpoint – persists block edits, accept/reject, ratings."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReviewEventORM
from app.db.session import get_db

router = APIRouter(prefix="/review", tags=["review"])


class ReviewEventIn(BaseModel):
    note_block_id: uuid.UUID
    action: str               # edit | accept | reject | rate
    before: str | None = None
    after: str | None = None
    user_rating: int | None = None  # 1-5


@router.post("/{session_id}")
async def submit_review_event(
    session_id: uuid.UUID,
    event: ReviewEventIn,
    db: AsyncSession = Depends(get_db),
):
    orm = ReviewEventORM(
        session_id=session_id,
        note_block_id=event.note_block_id,
        action=event.action,
        before=event.before,
        after=event.after,
        user_rating=event.user_rating,
        timestamp=datetime.utcnow(),
    )
    db.add(orm)
    await db.commit()
    return {"event_id": str(orm.id), "status": "recorded"}
