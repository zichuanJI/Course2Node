"""File upload and pipeline trigger endpoint."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.types import SessionStatus
from app.db.models import LectureSessionORM
from app.db.session import get_db
from app.storage.local import write_upload

ALLOWED_AUDIO = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/ogg", "audio/webm"}
ALLOWED_SLIDES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/pdf",
}
ALLOWED_CONTEXT = {"application/pdf", "text/plain"}

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/")
async def upload_lecture(
    course_title: str = Form(...),
    lecture_title: str = Form(...),
    language: str = Form("auto"),
    audio: UploadFile | None = File(None),
    slides: UploadFile | None = File(None),
    context_doc: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    if not audio and not slides:
        raise HTTPException(status_code=422, detail="At least one of audio or slides is required.")

    session_id = uuid.uuid4()
    source_files = []

    for upload, allowed in [
        (audio, ALLOWED_AUDIO),
        (slides, ALLOWED_SLIDES),
        (context_doc, ALLOWED_CONTEXT),
    ]:
        if upload is None:
            continue
        if upload.content_type not in allowed:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type for {upload.filename}: {upload.content_type}",
            )
        data = await upload.read()
        path = write_upload(session_id, upload.filename, data)
        source_files.append(
            {
                "file_id": str(uuid.uuid4()),
                "filename": upload.filename,
                "content_type": upload.content_type,
                "storage_path": str(path),
                "size_bytes": len(data),
                "uploaded_at": datetime.utcnow().isoformat(),
            }
        )

    orm = LectureSessionORM(
        id=session_id,
        course_title=course_title,
        lecture_title=lecture_title,
        language=language,
        status=SessionStatus.pending.value,
        source_files=source_files,
    )
    db.add(orm)
    await db.commit()

    # Trigger async pipeline
    from app.workers.tasks import run_full_pipeline
    run_full_pipeline.delay(str(session_id))

    return {"session_id": str(session_id), "status": "pending"}
