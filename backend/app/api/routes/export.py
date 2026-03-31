"""Note export endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.pipeline.export_renderer import get_renderer
from app.storage.local import read_artifact

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/{session_id}/{fmt}")
async def export_note(session_id: uuid.UUID, fmt: str):
    if fmt not in ("markdown", "tex", "txt"):
        raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")
    try:
        note_doc = read_artifact(session_id, "synthesize", version=1)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Note not yet generated for this session.")

    renderer = get_renderer(fmt)
    content = renderer.render(note_doc, fmt)

    media_type = {
        "markdown": "text/markdown",
        "tex": "application/x-tex",
        "txt": "text/plain",
    }[fmt]
    return PlainTextResponse(content, media_type=media_type)
