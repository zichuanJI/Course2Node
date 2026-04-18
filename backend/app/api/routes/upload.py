from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.types import CourseSession, SessionStatus, SourceFile, SourceKind, UploadResponse
from app.services.graph_builder import build_graph
from app.services.ingestion import ingest_source
from app.storage.local import delete_graph_artifact, delete_note, load_session, save_session, write_upload

ALLOWED_PDF = {"application/pdf"}
ALLOWED_AUDIO = {
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/ogg", "audio/webm", "audio/m4a",
}
ALLOWED_PDF_EXTENSIONS = {".pdf"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".wav", ".ogg", ".webm", ".m4a"}

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/pdf", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    course_title: str | None = Form(None),
    lecture_title: str | None = Form(None),
):
    return await _upload_source(
        kind=SourceKind.pdf,
        upload=file,
        session_id=session_id,
        course_title=course_title,
        lecture_title=lecture_title,
        allowed_types=ALLOWED_PDF,
    )


@router.post("/audio", response_model=UploadResponse)
async def upload_audio(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    course_title: str | None = Form(None),
    lecture_title: str | None = Form(None),
):
    return await _upload_source(
        kind=SourceKind.audio,
        upload=file,
        session_id=session_id,
        course_title=course_title,
        lecture_title=lecture_title,
        allowed_types=ALLOWED_AUDIO,
    )


@router.post("/pdfs")
async def upload_pdfs(
    files: list[UploadFile] = File(...),
    course_title: str = Form(...),
    lecture_title: str = Form(...),
    auto_ingest_and_build: bool = Form(True),
):
    if not files:
        raise HTTPException(status_code=422, detail="At least one PDF is required.")

    session = CourseSession(
        course_title=course_title,
        lecture_title=lecture_title,
        status=SessionStatus.draft,
    )
    save_session(session)

    source_ids: list[str] = []
    for upload in files:
        content_type = _validated_content_type(upload, ALLOWED_PDF, ALLOWED_PDF_EXTENSIONS)
        data = await upload.read()
        storage_path = write_upload(session.session_id, upload.filename, data)
        source = SourceFile(
            kind=SourceKind.pdf,
            filename=upload.filename,
            content_type=content_type,
            storage_path=str(storage_path),
            size_bytes=len(data),
            uploaded_at=datetime.utcnow(),
        )
        session.source_files.append(source)
        source_ids.append(str(source.source_id))

    _mark_session_for_rebuild(session)
    save_session(session)

    if auto_ingest_and_build:
        try:
            for source in session.source_files:
                ingest_source(session.session_id, source.source_id)
            graph = build_graph(session.session_id)
            return {
                "session_id": str(session.session_id),
                "source_ids": source_ids,
                "concept_count": len(graph.concepts),
                "edge_count": len(graph.edges),
                "cluster_count": len(graph.topic_clusters),
                "status": "graph_ready",
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "session_id": str(session.session_id),
        "source_ids": source_ids,
        "status": "uploaded",
    }


async def _upload_source(
    kind: SourceKind,
    upload: UploadFile,
    session_id: str | None,
    course_title: str | None,
    lecture_title: str | None,
    allowed_types: set[str],
) -> UploadResponse:
    allowed_extensions = ALLOWED_PDF_EXTENSIONS if kind == SourceKind.pdf else ALLOWED_AUDIO_EXTENSIONS
    content_type = _validated_content_type(upload, allowed_types, allowed_extensions)

    session = _resolve_session(session_id, course_title, lecture_title)
    data = await upload.read()
    storage_path = write_upload(session.session_id, upload.filename, data)

    source = SourceFile(
        kind=kind,
        filename=upload.filename,
        content_type=content_type,
        storage_path=str(storage_path),
        size_bytes=len(data),
        uploaded_at=datetime.utcnow(),
    )
    session.source_files.append(source)
    _mark_session_for_rebuild(session)
    save_session(session)

    return UploadResponse(
        session_id=session.session_id,
        source_id=source.source_id,
        kind=kind,
        status=session.status,
    )


def _resolve_session(
    session_id: str | None,
    course_title: str | None,
    lecture_title: str | None,
) -> CourseSession:
    if session_id:
        try:
            return load_session(uuid.UUID(session_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Session not found.") from exc

    if not course_title or not lecture_title:
        raise HTTPException(
            status_code=422,
            detail="course_title and lecture_title are required when creating a new session.",
        )

    session = CourseSession(
        course_title=course_title,
        lecture_title=lecture_title,
        status=SessionStatus.draft,
    )
    save_session(session)
    return session


def _validated_content_type(
    upload: UploadFile,
    allowed_types: set[str],
    allowed_extensions: set[str],
) -> str:
    content_type = (upload.content_type or "").lower()
    suffix = Path(upload.filename or "").suffix.lower()
    if content_type in allowed_types:
        return content_type
    if suffix in allowed_extensions:
        return content_type or "application/octet-stream"
    raise HTTPException(status_code=415, detail=f"Unsupported content type: {upload.content_type}")


def _mark_session_for_rebuild(session: CourseSession) -> None:
    delete_graph_artifact(session.session_id)
    delete_note(session.session_id)
    session.status = SessionStatus.uploaded
    session.error_message = None
    session.updated_at = datetime.utcnow()
    session.stats.document_count = sum(1 for source in session.source_files if source.kind == SourceKind.pdf)
    session.stats.audio_count = sum(1 for source in session.source_files if source.kind == SourceKind.audio)
    session.stats.chunk_count = 0
    session.stats.concept_count = 0
    session.stats.relation_count = 0
    session.stats.cluster_count = 0
