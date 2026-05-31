from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse

from app.services.chat import get_chat, render_chat_markdown
from app.storage.local import load_exam, load_note, load_session
from app.pipeline.export_renderer import get_renderer

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/{session_id}/exam/{fmt}")
async def export_exam(session_id: uuid.UUID, fmt: str):
    if fmt not in {"markdown", "txt", "tex", "pdf"}:
        raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")
    try:
        exam = load_exam(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No generated exam found for this session.") from exc

    renderer = get_renderer(fmt)
    content = renderer.render(exam.model_dump(), fmt)

    if fmt == "pdf":
        return Response(content, media_type="application/pdf", headers={
            "Content-Disposition": f"attachment; filename=exam_{session_id}.pdf"
        })
    
    media_type = {
        "markdown": "text/markdown",
        "txt": "text/plain",
        "tex": "application/x-tex",
    }[fmt]
    
    return PlainTextResponse(content, media_type=media_type)


@router.get("/{session_id}/chat/markdown")
async def export_chat(session_id: uuid.UUID):
    try:
        chat = get_chat(session_id)
        session = load_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc

    content = render_chat_markdown(chat, title=f"{session.lecture_title} - 对话记录")
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/{session_id}/{fmt}")
async def export_note(session_id: uuid.UUID, fmt: str):
    if fmt not in {"markdown", "txt", "tex", "pdf"}:
        raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")
    try:
        note = load_note(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No generated note found for this session.") from exc

    renderer = get_renderer(fmt)
    content = renderer.render(note.model_dump(), fmt)

    if fmt == "pdf":
        return Response(content, media_type="application/pdf", headers={
            "Content-Disposition": f"attachment; filename=notes_{session_id}.pdf"
        })

    media_type = {
        "markdown": "text/markdown",
        "txt": "text/plain",
        "tex": "application/x-tex",
    }[fmt]
    
    return PlainTextResponse(content, media_type=media_type)
