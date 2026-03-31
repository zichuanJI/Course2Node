"""Stage 6 – Export renderer.
Deterministically converts a NoteDocument JSON to Markdown / TeX / TXT.
"""
from __future__ import annotations

from app.core.providers import ExportRenderer
from app.core.types import GroundingLevel, NoteDocument


class MarkdownRenderer(ExportRenderer):
    def render(self, note_document: dict, fmt: str = "markdown") -> str:
        doc = NoteDocument.model_validate(note_document)
        lines: list[str] = []

        lines.append(f"# {doc.metadata.lecture_title}\n")
        lines.append(f"**Course:** {doc.metadata.course_title}  \n")
        lines.append(f"**Generated:** {doc.metadata.generated_at.date()}\n\n")

        if doc.one_paragraph_summary:
            lines.append(f"> {doc.one_paragraph_summary}\n\n")

        for section in doc.sections:
            lines.append(f"## {section.title}\n\n")
            for block in section.blocks:
                if block.title:
                    lines.append(f"### {block.title}\n\n")
                lines.append(block.content_md + "\n\n")
                if block.grounding_level == GroundingLevel.supplemental:
                    lines.append("*[Supplemental – external source]*\n\n")

        if doc.supplemental_context:
            lines.append("## Supplemental Context\n\n")
            for block in doc.supplemental_context:
                lines.append(f"> **[Supplemental]** {block.content_md}\n\n")

        if doc.key_terms:
            lines.append("## Key Terms\n\n")
            for term in doc.key_terms:
                lines.append(f"- **{term.title}**: {term.content_md}\n")
            lines.append("\n")

        if doc.open_questions:
            lines.append("## Open Questions\n\n")
            for q in doc.open_questions:
                lines.append(f"- {q.content_md}\n")

        return "".join(lines)


class TxtRenderer(ExportRenderer):
    def render(self, note_document: dict, fmt: str = "txt") -> str:
        md = MarkdownRenderer().render(note_document)
        # Strip markdown syntax for plain text
        import re
        text = re.sub(r"#{1,6}\s", "", md)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"> ", "", text)
        return text


class TexRenderer(ExportRenderer):
    def render(self, note_document: dict, fmt: str = "tex") -> str:
        doc = NoteDocument.model_validate(note_document)
        lines: list[str] = [
            r"\documentclass{article}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{hyperref}",
            r"\begin{document}",
            f"\\title{{{doc.metadata.lecture_title}}}",
            f"\\author{{{doc.metadata.course_title}}}",
            r"\maketitle",
        ]
        if doc.one_paragraph_summary:
            lines += [r"\begin{abstract}", doc.one_paragraph_summary, r"\end{abstract}"]

        for section in doc.sections:
            lines.append(f"\\section{{{section.title}}}")
            for block in section.blocks:
                if block.title:
                    lines.append(f"\\subsection{{{block.title}}}")
                lines.append(block.content_md)

        lines.append(r"\end{document}")
        return "\n".join(lines)


def get_renderer(fmt: str) -> ExportRenderer:
    return {
        "markdown": MarkdownRenderer(),
        "txt": TxtRenderer(),
        "tex": TexRenderer(),
    }[fmt]
