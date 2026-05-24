"""Stage 6 – Export renderer.
Deterministically converts a NoteDocument JSON to Markdown / TeX / TXT / PDF.
"""
from __future__ import annotations

import re
from typing import Any
from app.core.providers import ExportRenderer
from app.core.types import NoteDocument, ExamDocument


class MarkdownRenderer(ExportRenderer):
    def render(self, note_document: dict[str, Any], fmt: str = "markdown") -> str:
        # Check if it's an exam or a note
        if "questions" in note_document:
            return self._render_exam(ExamDocument.model_validate(note_document))
        return self._render_note(NoteDocument.model_validate(note_document))

    def _render_note(self, doc: NoteDocument) -> str:
        lines = [f"# {doc.title}", "", doc.summary, ""]
        for section in doc.sections:
            lines.extend([f"## {section.title}", "", section.content_md, ""])
        return "\n".join(lines).strip() + "\n"

    def _render_exam(self, exam: ExamDocument) -> str:
        lines = [f"# {exam.title}", "", exam.summary, "", "## 题目", ""]
        for index, question in enumerate(exam.questions, start=1):
            lines.extend([f"### {index}. {self._question_type_label(question.question_type)}", "", question.stem, ""])
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

    def _question_type_label(self, question_type: str) -> str:
        return {
            "single_choice": "单选题",
            "multiple_choice": "多选题",
            "true_false": "判断题",
            "fill_blank": "填空题",
            "short_answer": "简答题",
            "essay": "论述题",
        }.get(question_type, question_type)


class TxtRenderer(ExportRenderer):
    def render(self, note_document: dict[str, Any], fmt: str = "txt") -> str:
        md = MarkdownRenderer().render(note_document)
        # Strip markdown syntax for plain text
        text = re.sub(r"#{1,6}\s", "", md)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"> ", "", text)
        return text


class TexRenderer(ExportRenderer):
    def render(self, note_document: dict[str, Any], fmt: str = "tex") -> str:
        if "questions" in note_document:
            return self._render_exam_tex(ExamDocument.model_validate(note_document))
        return self._render_note_tex(NoteDocument.model_validate(note_document))

    def _render_note_tex(self, note: NoteDocument) -> str:
        sections = []
        for section in note.sections:
            body = self._md_to_tex(section.content_md)
            sections.append(f"\\section{{{self._tex_escape(section.title)}}}\n{body}")
        return "\n\n".join(
            [
                "\\documentclass{article}",
                "\\usepackage[utf8]{inputenc}",
                "\\usepackage{CJKutf8}",
                "\\usepackage{hyperref}",
                "\\usepackage{booktabs}",
                "\\begin{document}",
                "\\begin{CJK*}{UTF8}{gbsn}",
                f"\\title{{{self._tex_escape(note.title)}}}",
                "\\maketitle",
                self._md_to_tex(note.summary),
                *sections,
                "\\end{CJK*}",
                "\\end{document}",
            ]
        )

    def _render_exam_tex(self, exam: ExamDocument) -> str:
        question_blocks = []
        answer_blocks = []
        for index, question in enumerate(exam.questions, start=1):
            choices = "\n".join(f"\\item {self._tex_escape(choice.choice_id)}. {self._tex_escape(choice.text)}" for choice in question.choices)
            choice_block = f"\n\\begin{{itemize}}\n{choices}\n\\end{{itemize}}" if choices else ""
            question_blocks.append(
                f"\\subsection*{{{index}. {self._question_type_label(question.question_type)}}}\n"
                f"{self._md_to_tex(question.stem)}{choice_block}"
            )
            answer_blocks.append(
                f"\\subsection*{{{index}. 答案}}\n"
                f"答案：{self._tex_escape(question.answer)}\n\n"
                f"解析：{self._md_to_tex(question.explanation)}"
            )
        return "\n\n".join(
            [
                "\\documentclass{article}",
                "\\usepackage[utf8]{inputenc}",
                "\\usepackage{CJKutf8}",
                "\\usepackage{hyperref}",
                "\\begin{document}",
                "\\begin{CJK*}{UTF8}{gbsn}",
                f"\\title{{{self._tex_escape(exam.title)}}}",
                "\\maketitle",
                self._md_to_tex(exam.summary),
                "\\section*{题目}",
                *question_blocks,
                "\\section*{答案与解析}",
                *answer_blocks,
                "\\end{CJK*}",
                "\\end{document}",
            ]
        )

    def _question_type_label(self, question_type: str) -> str:
        return MarkdownRenderer()._question_type_label(question_type)

    def _tex_escape(self, text: str) -> str:
        return (
            text.replace("\\", "\\textbackslash{}")
            .replace("_", "\\_")
            .replace("&", "\\&")
            .replace("%", "\\%")
            .replace("#", "\\#")
            .replace("$", "\\$")
            .replace("{", "\\{")
            .replace("}", "\\}")
        )

    def _md_to_tex(self, md: str) -> str:
        # Very basic markdown to latex converter
        tex = md
        # Escape special chars first (but preserve $ for math if needed - though current system uses $$)
        # For simplicity, we'll just escape most and handle bold/italic/lists
        tex = self._tex_escape(tex)
        
        # Bold: **text** -> \textbf{text}
        tex = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", tex)
        # Italic: *text* -> \textit{text}
        tex = re.sub(r"\*(.+?)\*", r"\\textit{\1}", tex)
        
        # Unordered list: - item -> \item item (needs env wrapper)
        # This is tricky for multiline. We'll just do a very basic replacement.
        # Tables are even harder. 
        return tex


class PdfRenderer(ExportRenderer):
    """Generate PDF via xhtml2pdf with registered system CJK TrueType fonts.

    The default CID font (STSong-Light) in ReportLab causes every CJK character
    to be rendered in a fixed-width cell with extra whitespace.  By registering
    system TrueType fonts (SimSun / SimHei on Windows) we get proper kerning,
    correct character spacing, and real bold rendering.
    """

    _fonts_ready = False
    _body_font = "Microsoft YaHei", "SimSun"
    _bold_font = "Microsoft YaHei", "SimSun"

    # ------------------------------------------------------------------
    # Font registration (run once)
    # ------------------------------------------------------------------

    @classmethod
    def _ensure_fonts(cls) -> None:
        if cls._fonts_ready:
            return
        cls._fonts_ready = True

        import os

        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.lib.fonts import addMapping
        except ImportError:
            return

        font_dir = os.path.join(
            os.environ.get("SystemRoot", os.environ.get("WINDIR", r"C:\Windows")),
            "Fonts",
        )

        # --- Body font: SimSun (宋体) ---
        for candidate, idx in [("simsun.ttc", 0), ("SIMSUN.TTC", 0), ("SimSun.ttf", None)]:
            path = os.path.join(font_dir, candidate)
            if not os.path.exists(path):
                continue
            try:
                if idx is not None:
                    pdfmetrics.registerFont(TTFont("SimSun", path, subfontIndex=idx))
                else:
                    pdfmetrics.registerFont(TTFont("SimSun", path))
                cls._body_font = "SimSun"
                break
            except Exception:
                continue

        # --- Bold / Heading font: SimHei (黑体) ---
        for candidate in ["simhei.ttf", "SIMHEI.TTF"]:
            path = os.path.join(font_dir, candidate)
            if not os.path.exists(path):
                continue
            try:
                pdfmetrics.registerFont(TTFont("SimHei", path))
                cls._bold_font = "SimHei"
                break
            except Exception:
                continue

        # --- Map bold weight: SimSun bold -> SimHei ---
        if cls._body_font == "SimSun" and cls._bold_font == "SimHei":
            try:
                addMapping("SimSun", 0, 0, "SimSun")   # normal
                addMapping("SimSun", 1, 0, "SimHei")   # bold
                addMapping("SimSun", 0, 1, "SimSun")   # italic  (no italic variant)
                addMapping("SimSun", 1, 1, "SimHei")   # bold-italic
            except Exception:
                pass

            # xhtml2pdf has its own internal font registry (DEFAULT_FONT).
            # Even though we register SimSun/SimHei with ReportLab's
            # pdfmetrics above, xhtml2pdf never queries pdfmetrics – it
            # only looks in its DEFAULT_FONT dict and asianFontList.
            # We therefore inject our custom font names so the CSS
            # font-family stack actually uses real TrueType fonts.
            try:
                import xhtml2pdf.default as _x2p_default
                _x2p_default.DEFAULT_FONT["simsun"] = "SimSun"
                _x2p_default.DEFAULT_FONT["simhei"] = "SimHei"
            except Exception:
                pass

    # ------------------------------------------------------------------
    # PDF engine detection (run once)
    # ------------------------------------------------------------------

    _wkhtmltopdf_path: str | None = None
    _engine: str = ""  # "wkhtmltopdf" | "xhtml2pdf"

    @classmethod
    def _detect_engine(cls) -> str:
        if cls._engine:
            return cls._engine

        import os
        import shutil

        # 1) Explicit config setting takes priority
        from app.config import settings
        configured = settings.wkhtmltopdf_path.strip()
        if configured and os.path.exists(configured):
            cls._wkhtmltopdf_path = configured
            cls._engine = "wkhtmltopdf"
            return cls._engine

        # 2) Check common install paths on Windows
        for candidate in [
            r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
            r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
        ]:
            if os.path.exists(candidate):
                cls._wkhtmltopdf_path = candidate
                cls._engine = "wkhtmltopdf"
                return cls._engine

        # 3) Check PATH
        found = shutil.which("wkhtmltopdf")
        if found:
            cls._wkhtmltopdf_path = found
            cls._engine = "wkhtmltopdf"
            return cls._engine

        cls._engine = "xhtml2pdf"
        return cls._engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, note_document: dict[str, Any], fmt: str = "pdf") -> bytes:
        import markdown  # pyrefly: ignore[missing-import]
        from io import BytesIO

        self._ensure_fonts()

        if "questions" in note_document:
            md_content = MarkdownRenderer()._render_exam(ExamDocument.model_validate(note_document))
            title = note_document.get("title", "Exam")
        else:
            md_content = MarkdownRenderer()._render_note(NoteDocument.model_validate(note_document))
            title = note_document.get("title", "Notes")

        md_content = self._sanitize_for_pdf(md_content)
        md_content = self._fix_list_separation(md_content)

        html_body = markdown.markdown(
            md_content,
            extensions=["tables", "fenced_code", "toc"],
        )

        html_body = self._enhance_html_structure(html_body)
        html_body = self._number_sections(html_body)

        engine = self._detect_engine()

        # CJK wrap is only needed for xhtml2pdf fallback.
        # wkhtmltopdf (WebKit) handles CJK text natively.
        if engine != "wkhtmltopdf":
            html_body = self._fix_cjk_wrap(html_body)

        full_html = self._build_html_template(title, html_body)

        if engine == "wkhtmltopdf":
            return self._render_with_wkhtmltopdf(full_html)
        else:
            return self._render_with_xhtml2pdf(full_html)

    def _render_with_wkhtmltopdf(self, html: str) -> bytes:
        import pdfkit
        from io import BytesIO

        options = {
            "page-size": "A4",
            "margin-top": "12mm",
            "margin-right": "12mm",
            "margin-bottom": "12mm",
            "margin-left": "12mm",
            "encoding": "UTF-8",
            "no-outline": None,
            "enable-local-file-access": None,
        }

        config = pdfkit.configuration(wkhtmltopdf=self._wkhtmltopdf_path)
        result = pdfkit.from_string(html, False, options=options, configuration=config)
        return result

    def _render_with_xhtml2pdf(self, html: str) -> bytes:
        from io import BytesIO
        from xhtml2pdf import pisa  # pyrefly: ignore[missing-import]

        result = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=result, encoding="utf-8")

        if pisa_status.err:
            raise RuntimeError(f"PDF generation failed: {pisa_status.err}")

        return result.getvalue()

    # ------------------------------------------------------------------
    # HTML post-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _fix_cjk_wrap(html: str) -> str:
        """Insert zero-width break opportunities between CJK characters.

        ReportLab's paragraph engine wraps text at word boundaries (spaces),
        but CJK text has no spaces.  Without break points, long CJK lines
        overflow and get truncated.  We insert U+200B (zero-width space)
        between CJK characters to create line-break candidates.
        """
        # The replacement for text runs: insert ZWSP after every CJK char
        # except when the NEXT char is also in a "no-break" set (ASCII, digits).
        ZWSP = "\u200b"
        CJK_RANGES = [
            (0x4E00, 0x9FFF),   # CJK Unified Ideographs
            (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
            (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
            (0x3000, 0x303F),   # CJK Symbols and Punctuation
            (0xFF00, 0xFFEF),   # Halfwidth and Fullwidth Forms
        ]

        def _is_cjk(cp: int) -> bool:
            for lo, hi in CJK_RANGES:
                if lo <= cp <= hi:
                    return True
            return False

        def _insert_breaks(text: str) -> str:
            result: list[str] = []
            length = len(text)
            i = 0
            while i < length:
                ch = text[i]
                result.append(ch)
                cp = ord(ch)
                if _is_cjk(cp) and i + 1 < length:
                    next_cp = ord(text[i + 1])
                    if next_cp not in (0x200B, 0xFEFF) and ch != "\n":
                        result.append(ZWSP)
                i += 1
            return "".join(result)

        # Split HTML into tags and text runs.  Text runs are everything BETWEEN
        # tags.  We must NOT modify content inside <pre> or <code> blocks.
        parts = re.split(r"(<[^>]+>)", html)

        in_pre = False
        for i, part in enumerate(parts):
            if part.startswith("<"):
                lower = part.lower()
                if lower.startswith("<pre") or lower.startswith("<code"):
                    in_pre = True
                elif lower.startswith("</pre") or lower.startswith("</code"):
                    in_pre = False
                continue

            if in_pre:
                continue

            parts[i] = _insert_breaks(part)

        return "".join(parts)

    @staticmethod
    def _enhance_html_structure(html: str) -> str:
        """Add CSS classes to standalone bold lines used as sub-headings."""

        def _sub_heading_replacer(m: re.Match[str]) -> str:
            inner = m.group(1)
            css_class = "sub-heading"
            lower = inner.lower()
            if any(kw in lower for kw in ("关键结论", "核心结论", "总结")):
                css_class += " conclusion"
            elif any(kw in lower for kw in ("学习路径", "建议学习")):
                css_class += " learning-path"
            elif any(kw in lower for kw in ("易混点", "易混淆", "注意")):
                css_class += " caution"
            elif any(kw in lower for kw in ("核心问题",)):
                css_class += " core-question"
            return f'<p class="{css_class}"><strong>{inner}</strong></p>'

        html = re.sub(
            r"<p>\s*<strong>([^<]+?)</strong>\s*</p>",
            _sub_heading_replacer,
            html,
        )
        return html

    # ------------------------------------------------------------------
    # Markdown pre-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _fix_list_separation(md_text: str) -> str:
        """Insert blank lines before list items that follow non-list lines.

        The markdown library requires a blank line between a paragraph and a
        list to produce <ul>/<ol> elements.  LLM-generated notes often omit
        those blank lines (e.g. \"text：\\n- item\"), causing list items to be
        rendered as literal \"- text\" inside a <p> tag instead.
        """
        lines = md_text.split("\n")
        result: list[str] = []
        in_code_block = False
        _list_re = re.compile(r"^(\s*)([-*+]|\d+\.)\s")

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Track fenced code blocks – do not touch content inside them
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                result.append(line)
                i += 1
                continue

            if in_code_block:
                result.append(line)
                i += 1
                continue

            # Is this line a list item?
            is_list_item = bool(_list_re.match(line))

            if is_list_item and result:
                prev = result[-1]
                if prev != "" and not _list_re.match(prev):
                    result.append("")  # blank-line separator

            result.append(line)
            i += 1

        return "\n".join(result)

    # ------------------------------------------------------------------
    # Content sanitisation
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_for_pdf(text: str) -> str:
        """Remove emoji and unsupported Unicode characters for PDF fonts.

        SimSun/SimHei TrueType fonts do not contain glyphs for emoji
        (U+1F000+) or dingbat symbols (U+2700-U+27BF).  We keep all
        other BMP characters since SimSun has broad coverage.
        """
        result: list[str] = []
        for ch in text:
            cp = ord(ch)
            if cp > 0xFFFF:
                # Everything above BMP → emoji / pictographs: strip
                continue
            if 0x2700 <= cp <= 0x27BF:
                # Dingbat symbols missing in SimSun
                continue
            result.append(ch)
        return "".join(result)

    @classmethod
    def _number_sections(cls, html: str) -> str:
        """Prefix h2 elements with auto-incrementing section numbers."""
        counter = [0]

        def _add_number(m: re.Match[str]) -> str:
            counter[0] += 1
            tag_start = m.group(1)
            inner = m.group(2)
            return f"{tag_start}{counter[0]}　{inner}</h2>"

        html = re.sub(r"(<h2[^>]*>)(.+?)</h2>", _add_number, html)
        return html

    # ------------------------------------------------------------------
    # HTML + CSS template  (tuned for xhtml2pdf CSS support)
    # ------------------------------------------------------------------

    @classmethod
    def _build_html_template(cls, title: str, body: str) -> str:
        bf = cls._body_font
        hf = cls._bold_font

        return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
/* === Page === */
@page {{
    size: A4;
    margin: 1.2cm 1.2cm 1.2cm 1.2cm;
}}

/* === Base === */
body {{
    font-family: "{bf}", "Microsoft YaHei", serif;
    font-size: 10pt;
    color: #2b2621;
    line-height: 1.75;
    width: 100%;
}}

/* === Main Title (h1) === */
h1 {{
    font-family: "{hf}", "Microsoft YaHei", "{bf}", sans-serif;
    font-size: 20pt;
    font-weight: bold;
    color: #1a1612;
    border-bottom: 2.5px solid #b25a2d;
    padding-bottom: 12px;
    margin-top: 0;
    margin-bottom: 24px;
}}

/* === Section Title (h2) — auto-numbered by _number_sections === */
h2 {{
    font-family: "{hf}", "Microsoft YaHei", "{bf}", sans-serif;
    font-size: 15pt;
    font-weight: bold;
    color: #1a1612;
    margin-top: 36px;
    margin-bottom: 16px;
    padding: 6px 0 8px 0;
    border-bottom: 2px solid #c7baa2;
    page-break-before: auto;
}}

/* === Sub-section Title (h3) === */
h3 {{
    font-family: "{hf}", "Microsoft YaHei", "{bf}", sans-serif;
    font-size: 12.5pt;
    font-weight: bold;
    color: #3a2e22;
    margin-top: 24px;
    margin-bottom: 10px;
    padding-left: 12px;
    border-left: 3px solid #d4a574;
}}

h4 {{
    font-family: "{hf}", "Microsoft YaHei", "{bf}", sans-serif;
    font-size: 11.5pt;
    font-weight: bold;
    color: #5a4a3a;
    margin-top: 18px;
    margin-bottom: 8px;
}}

/* === Paragraphs === */
p {{
    margin: 6px 0;
    text-align: left;
}}

/* === Bold keywords === */
strong, b {{
    font-family: "{hf}", "Microsoft YaHei", "{bf}", sans-serif;
    font-weight: bold;
    color: #1a1612;
}}

/* === Bold sub-heading blocks (LLM **关键结论** etc.) === */
.sub-heading {{
    margin-top: 20px;
    margin-bottom: 10px;
    padding: 8px 12px;
    background-color: #f6f3ed;
    border-left: 4px solid #8e8e8e;
    border-radius: 0;
}}
.sub-heading strong {{
    font-size: 12pt;
    font-family: "{hf}", "Microsoft YaHei", "{bf}", sans-serif;
}}

.conclusion {{
    background-color: #f7f2ea;
    border-left-color: #b25a2d;
}}
.conclusion strong {{
    color: #8e4420;
}}

.learning-path {{
    background-color: #edf4ea;
    border-left-color: #4a7a4a;
}}
.learning-path strong {{
    color: #3d6a3d;
}}

.caution {{
    background-color: #fef7ec;
    border-left-color: #d49a2a;
}}
.caution strong {{
    color: #9a6d1e;
}}

.core-question {{
    background-color: #edf0f9;
    border-left-color: #2c5ec6;
}}
.core-question strong {{
    color: #2c5ec6;
}}

/* === Inline code === */
code {{
    font-family: "Courier New", monospace;
    font-size: 9.5pt;
    color: #b14a40;
    background-color: #f6f2ee;
    border: 1px solid #ddd5ca;
    padding: 1px 4px;
}}

/* === Code blocks === */
pre {{
    background-color: #faf8f5;
    border: 1px solid #e4dccd;
    padding: 10px 14px;
    margin: 12px 0;
    font-family: "Courier New", monospace;
    font-size: 9pt;
    line-height: 1.5;
}}
pre code {{
    background-color: transparent;
    border: none;
    padding: 0;
    color: #2b2621;
}}

/* === Lists === */
ul {{
    margin: 6px 0 6px 22px;
    padding: 0;
}}
ol {{
    margin: 6px 0 6px 22px;
    padding: 0;
}}
li {{
    margin: 5px 0;
    line-height: 1.7;
    text-align: left;
}}

/* === Tables === */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 9pt;
}}
th {{
    background-color: #f0e8da;
    color: #3a2e22;
    font-family: "{hf}", "Microsoft YaHei", "{bf}", sans-serif;
    font-weight: bold;
    text-align: left;
    padding: 6px 8px;
    border: 1px solid #c7baa2;
}}
td {{
    padding: 5px 8px;
    border: 1px solid #ddd5ca;
    line-height: 1.55;
    vertical-align: top;
}}

/* === Blockquotes === */
blockquote {{
    margin: 14px 0;
    padding: 8px 16px;
    background-color: #f7f2ea;
    border-left: 4px solid #b25a2d;
    color: #3a322a;
}}
blockquote p {{
    margin: 4px 0;
}}

/* === Horizontal rules === */
hr {{
    border: none;
    height: 1px;
    background-color: #ddd5ca;
    margin: 22px 0;
}}

/* === KaTeX / Math blocks === */
.katex-display {{
    margin: 12px 0;
}}
</style>
</head>
<body>
{body}
</body>
</html>"""


def get_renderer(fmt: str) -> ExportRenderer:
    return {
        "markdown": MarkdownRenderer(),
        "txt": TxtRenderer(),
        "tex": TexRenderer(),
        "pdf": PdfRenderer(),
    }[fmt]

