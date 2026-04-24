from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.services.text_utils import normalize_text

KIMI_PDF_SYSTEM_PROMPT = """\
你是课堂 PDF 内容提取器。你会读取若干页课程 slides / notes 的页面图像，并输出结构化 JSON。

要求：
- 忠实提取页面中的正文、标题、项目符号、公式周围的文字说明
- 删除页眉页脚、页码、学校署名、重复标题、装饰性文本
- 不要总结整页，不要脑补未出现的内容
- 如果一页几乎没有有效文字，body_text 返回空字符串
- 只返回 JSON object
"""


class ExtractedPdfPage(BaseModel):
    page_index: int
    page_title: str = ""
    body_text: str = ""
    bullets: list[str] = Field(default_factory=list)


class ExtractedPdfPages(BaseModel):
    pages: list[ExtractedPdfPage] = Field(default_factory=list)


@dataclass
class PdfPageImage:
    page_index: int
    image_bytes: bytes


@dataclass
class ExtractedPdfTextBlock:
    text: str
    page_index: int | None = None


def kimi_pdf_configured() -> bool:
    return bool(settings.kimi_api_key and settings.kimi_model)


def extract_pdf_text_with_kimi(filename: str, pdf_path: str | Path) -> list[ExtractedPdfTextBlock]:
    provider = OpenAICompatibleLLMProvider(
        api_key=settings.kimi_api_key,
        model=settings.kimi_model,
        base_url=settings.kimi_base_url,
        timeout_seconds=settings.kimi_timeout_seconds,
        max_output_tokens=settings.kimi_max_output_tokens,
    )
    try:
        extracted_text = provider.extract_file_content(pdf_path, purpose="file-extract")
    except Exception as exc:
        raise RuntimeError(f"Kimi PDF extraction failed for {filename}: {exc}") from exc
    file_blocks = split_kimi_file_content(extracted_text)
    if file_blocks and all(block.page_index is not None for block in file_blocks):
        return file_blocks

    page_blocks = _extract_pdf_text_by_page_images(filename, pdf_path)
    if page_blocks:
        return page_blocks

    if not file_blocks:
        raise RuntimeError(f"Kimi PDF extraction returned no usable text for {filename}.")
    return file_blocks


def split_kimi_file_content(text: str) -> list[ExtractedPdfTextBlock]:
    structured_blocks, unwrapped_text = _unwrap_kimi_file_content(text)
    if structured_blocks:
        return structured_blocks

    expanded = _expand_escaped_whitespace(unwrapped_text)
    if not normalize_text(expanded):
        return []

    markers = list(
        re.finditer(
            r"(?im)^\s*(?:#{1,6}\s*)?(?:-{2,}\s*)?(?:page|p\.|第)\s*(\d{1,4})\s*(?:页)?\s*(?:[:：])?\s*(?:-{2,})?\s*$",
            expanded,
        )
    )
    blocks: list[ExtractedPdfTextBlock] = []
    if markers:
        for index, marker in enumerate(markers):
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(expanded)
            page_text = normalize_text(expanded[start:end])
            if page_text:
                blocks.append(ExtractedPdfTextBlock(text=page_text, page_index=int(marker.group(1))))
        if blocks:
            return blocks

    return [ExtractedPdfTextBlock(text=normalize_text(expanded))]


def extract_pdf_pages_with_kimi(filename: str, pages: list[PdfPageImage]) -> list[ExtractedPdfPage]:
    if not pages:
        return []

    provider = OpenAICompatibleLLMProvider(
        api_key=settings.kimi_api_key,
        model=settings.kimi_model,
        base_url=settings.kimi_base_url,
        timeout_seconds=settings.kimi_timeout_seconds,
        max_output_tokens=settings.kimi_max_output_tokens,
    )

    prompt_lines = [
        f"请抽取课堂 PDF《{filename}》以下页面的文字内容。",
        "按 JSON 返回：",
        '{"pages":[{"page_index":1,"page_title":"","body_text":"","bullets":["..."]}]}',
        "注意：page_index 必须和输入页码一致；body_text 保留自然段；bullets 只放真正的要点或列表项。",
        "输入页面：",
    ]
    images: list[dict[str, str]] = []
    for page in pages:
        prompt_lines.append(f"- 第 {page.page_index} 页")
        images.append({"data_url": _png_data_url(page.image_bytes)})

    payload = provider.generate_json_from_images(
        prompt="\n".join(prompt_lines),
        system=KIMI_PDF_SYSTEM_PROMPT,
        images=images,
        temperature=1.0,  # kimi-k2.6 only accepts temperature=1
    )
    parsed = ExtractedPdfPages.model_validate(payload)
    normalized = {page.page_index: _normalize_page(page) for page in parsed.pages}
    return [normalized.get(page.page_index, ExtractedPdfPage(page_index=page.page_index)) for page in pages]


def render_page_text(page: ExtractedPdfPage) -> str:
    parts: list[str] = []
    if page.page_title:
        parts.append(page.page_title)
    if page.body_text:
        parts.append(page.body_text)
    if page.bullets:
        parts.extend(f"- {item}" for item in page.bullets)
    return normalize_text("\n".join(parts))


def _extract_pdf_text_by_page_images(filename: str, pdf_path: str | Path) -> list[ExtractedPdfTextBlock]:
    try:
        page_images = _render_pdf_page_images(pdf_path)
    except Exception:
        return []

    blocks: list[ExtractedPdfTextBlock] = []
    batch_size = max(1, settings.kimi_max_pages_per_call)
    for start in range(0, len(page_images), batch_size):
        batch = page_images[start:start + batch_size]
        pages = _extract_pdf_pages_batch_with_fallback(filename, batch)
        for page in pages:
            text = render_page_text(page)
            if text:
                blocks.append(ExtractedPdfTextBlock(text=text, page_index=page.page_index))
    return blocks


def _extract_pdf_pages_batch_with_fallback(filename: str, pages: list[PdfPageImage]) -> list[ExtractedPdfPage]:
    try:
        return extract_pdf_pages_with_kimi(filename, pages)
    except Exception:
        if len(pages) <= 1:
            return []

    extracted: list[ExtractedPdfPage] = []
    for page in pages:
        try:
            extracted.extend(extract_pdf_pages_with_kimi(filename, [page]))
        except Exception:
            continue
    return extracted


def _render_pdf_page_images(pdf_path: str | Path) -> list[PdfPageImage]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("package `pymupdf` is required to render PDF pages for Kimi page extraction") from exc

    images: list[PdfPageImage] = []
    with fitz.open(str(pdf_path)) as document:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            images.append(PdfPageImage(page_index=page_index + 1, image_bytes=pixmap.tobytes("png")))
    return images


def _unwrap_kimi_file_content(text: str) -> tuple[list[ExtractedPdfTextBlock], str]:
    payload = _try_load_json(text)
    if payload is None:
        return [], text

    blocks = _extract_structured_text_blocks(payload)
    if blocks:
        return blocks, ""

    content = _first_string_value(payload, ("content", "text", "markdown", "body"))
    if content:
        nested_payload = _try_load_json(content)
        if nested_payload is not None:
            nested_blocks = _extract_structured_text_blocks(nested_payload)
            if nested_blocks:
                return nested_blocks, ""
            nested_content = _first_string_value(nested_payload, ("content", "text", "markdown", "body"))
            if nested_content:
                return [], nested_content
        return [], content

    return [], text


def _try_load_json(text: str) -> Any | None:
    candidate = text.strip()
    if not candidate:
        return None
    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _extract_structured_text_blocks(payload: Any) -> list[ExtractedPdfTextBlock]:
    if isinstance(payload, list):
        blocks: list[ExtractedPdfTextBlock] = []
        for item in payload:
            blocks.extend(_extract_structured_text_blocks(item))
        return blocks

    if not isinstance(payload, dict):
        return []

    page_index = _extract_page_index(payload)
    page_text = _extract_text_from_mapping(payload)
    if page_index is not None and page_text:
        return [ExtractedPdfTextBlock(text=page_text, page_index=page_index)]

    blocks: list[ExtractedPdfTextBlock] = []
    for key in ("pages", "page_contents", "chunks", "items", "contents", "data", "result"):
        value = payload.get(key)
        if isinstance(value, (list, dict)):
            blocks.extend(_extract_structured_text_blocks(value))
    return blocks


def _extract_page_index(payload: dict[str, Any]) -> int | None:
    for key in ("page_index", "page_number", "page_no", "page", "p"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            page_index = int(str(value).strip())
        except ValueError:
            continue
        return max(1, page_index)
    return None


def _extract_text_from_mapping(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("page_title", "title"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("body_text", "text", "content", "page_content", "markdown"):
        value = payload.get(key)
        value_text = _stringify_text_value(value)
        if value_text:
            parts.append(value_text)
    for key in ("bullets", "items", "paragraphs"):
        value = payload.get(key)
        value_text = _stringify_text_value(value)
        if value_text:
            parts.append(value_text)
    return normalize_text("\n".join(parts))


def _stringify_text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_stringify_text_value(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return _extract_text_from_mapping(value)
    return ""


def _first_string_value(payload: Any, keys: tuple[str, ...]) -> str:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _expand_escaped_whitespace(text: str) -> str:
    return text.replace("\\r", "\n").replace("\\n", "\n").replace("\\t", "\t")


def _normalize_page(page: ExtractedPdfPage) -> ExtractedPdfPage:
    return ExtractedPdfPage(
        page_index=page.page_index,
        page_title=normalize_text(page.page_title),
        body_text=normalize_text(page.body_text),
        bullets=_clean_lines(page.bullets),
    )


def _clean_lines(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = normalize_text(item)
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(value[:220])
    return cleaned[:8]


def _png_data_url(image_bytes: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}"
