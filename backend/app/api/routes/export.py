from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.storage.local import load_exam, load_note

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/{session_id}/exam/{fmt}")
async def export_exam(session_id: uuid.UUID, fmt: str):
    if fmt not in {"markdown", "txt", "tex"}:
        raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")
    try:
        exam = load_exam(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No generated exam found for this session.") from exc

    if fmt == "markdown":
        content = _render_exam_markdown(exam)
        media_type = "text/markdown"
    elif fmt == "txt":
        content = _render_exam_text(exam)
        media_type = "text/plain"
    else:
        content = _render_exam_tex(exam)
        media_type = "application/x-tex"
    return PlainTextResponse(content, media_type=media_type)


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


def _render_exam_markdown(exam) -> str:
    lines = [f"# {exam.title}", "", exam.summary, "", "## 题目", ""]
    for index, question in enumerate(exam.questions, start=1):
        lines.extend([f"### {index}. {_question_type_label(question.question_type)}", "", question.stem, ""])
        for choice in question.choices:
            lines.append(f"- {choice.choice_id}. {choice.text}")
        if question.choices:
            lines.append("")
    lines.extend(["## 答案与解析", ""])
    for index, question in enumerate(exam.questions, start=1):
        lines.extend(
            [
                f"### {index}. 答案",
                "",
                f"答案：{question.answer}",
                "",
                f"解析：{question.explanation}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _render_exam_text(exam) -> str:
    lines = [exam.title, "", exam.summary, "", "题目", ""]
    for index, question in enumerate(exam.questions, start=1):
        lines.extend([f"{index}. [{_question_type_label(question.question_type)}] {question.stem}"])
        for choice in question.choices:
            lines.append(f"   {choice.choice_id}. {choice.text}")
        lines.append("")
    lines.extend(["答案与解析", ""])
    for index, question in enumerate(exam.questions, start=1):
        lines.extend([f"{index}. 答案：{question.answer}", f"   解析：{question.explanation}", ""])
    return "\n".join(lines).strip() + "\n"


def _render_exam_tex(exam) -> str:
    question_blocks = []
    answer_blocks = []
    for index, question in enumerate(exam.questions, start=1):
        choices = "\n".join(f"\\item {_tex_escape(choice.choice_id)}. {_tex_escape(choice.text)}" for choice in question.choices)
        choice_block = f"\n\\begin{{itemize}}\n{choices}\n\\end{{itemize}}" if choices else ""
        question_blocks.append(
            f"\\subsection*{{{index}. {_question_type_label(question.question_type)}}}\n"
            f"{_tex_escape(question.stem)}{choice_block}"
        )
        answer_blocks.append(
            f"\\subsection*{{{index}. 答案}}\n"
            f"答案：{_tex_escape(question.answer)}\n\n"
            f"解析：{_tex_escape(question.explanation)}"
        )
    return "\n\n".join(
        [
            "\\documentclass{article}",
            "\\begin{document}",
            f"\\title{{{_tex_escape(exam.title)}}}",
            "\\maketitle",
            _tex_escape(exam.summary),
            "\\section*{题目}",
            *question_blocks,
            "\\section*{答案与解析}",
            *answer_blocks,
            "\\end{document}",
        ]
    )


def _question_type_label(question_type: str) -> str:
    return {
        "single_choice": "单选题",
        "multiple_choice": "多选题",
        "true_false": "判断题",
        "fill_blank": "填空题",
        "short_answer": "简答题",
        "essay": "论述题",
    }.get(question_type, question_type)


def _tex_escape(text: str) -> str:
    return (
        text.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("#", "\\#")
    )
