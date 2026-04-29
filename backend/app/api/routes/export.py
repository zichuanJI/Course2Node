from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.storage.local import load_note

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/{session_id}/{fmt}")
async def export_note(session_id: uuid.UUID, fmt: str):
    if fmt not in {"markdown", "txt", "tex"}:
        raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")
    try:
        note = load_note(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No generated note found for this session.") from exc

    if fmt == "markdown":
        content = _render_markdown(note)
        media_type = "text/markdown"
    elif fmt == "txt":
        content = _render_text(note)
        media_type = "text/plain"
    else:
        content = _render_tex(note)
        media_type = "application/x-tex"
    return PlainTextResponse(content, media_type=media_type)


def _render_markdown(note) -> str:
    lines = [f"# {note.title}", "", note.summary, ""]
    for section in note.sections:
        lines.extend([f"## {section.title}", "", section.content_md, ""])
    return "\n".join(lines).strip() + "\n"


def _render_text(note) -> str:
    lines = [note.title, "", note.summary, ""]
    for section in note.sections:
        lines.extend([section.title, "-" * len(section.title), section.content_md, ""])
    return "\n".join(lines).strip() + "\n"


def _render_tex(note) -> str:
    sections = []
    for section in note.sections:
        body = section.content_md.replace("_", "\\_")
        sections.append(f"\\section{{{section.title}}}\n{body}")
    return "\n\n".join(
        [
            "\\documentclass{article}",
            "\\begin{document}",
            f"\\title{{{note.title}}}",
            "\\maketitle",
            note.summary.replace("_", "\\_"),
            *sections,
            "\\end{document}",
        ]
    )
