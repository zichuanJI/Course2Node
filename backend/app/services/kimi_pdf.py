from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.services.text_utils import normalize_text


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
    file_blocks = [
        ExtractedPdfTextBlock(text=block.text)
        for block in split_kimi_file_content(extracted_text)
        if normalize_text(block.text)
    ]
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
                blocks.append(ExtractedPdfTextBlock(text=page_text))
        if blocks:
            return blocks

    return [ExtractedPdfTextBlock(text=normalize_text(expanded))]


def _unwrap_kimi_file_content(text: str) -> tuple[list[ExtractedPdfTextBlock], str]:
    payload = _try_load_json(text)
    if payload is None:
        return [], text

    wrapper_content = _wrapper_string_content(payload)
    if wrapper_content:
        nested_payload = _try_load_json(wrapper_content)
        if nested_payload is not None:
            nested_blocks = _extract_structured_text_blocks(nested_payload)
            if nested_blocks:
                return nested_blocks, ""
            nested_content = _wrapper_string_content(nested_payload) or _first_string_value(
                nested_payload,
                ("content", "text", "markdown", "body"),
            )
            if nested_content:
                return [], nested_content
        return [], wrapper_content

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

    page_text = _extract_text_from_mapping(payload)
    if page_text:
        return [ExtractedPdfTextBlock(text=page_text)]

    blocks: list[ExtractedPdfTextBlock] = []
    for key in ("pages", "page_contents", "chunks", "items", "contents", "data", "result"):
        value = payload.get(key)
        if isinstance(value, (list, dict)):
            blocks.extend(_extract_structured_text_blocks(value))
    return blocks


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


def _wrapper_string_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    container_keys = {"pages", "page_contents", "chunks", "items", "contents", "data", "result"}
    if any(key in payload for key in container_keys):
        return ""
    metadata_keys = {"filename", "file_name", "type", "status"}
    content_keys = ("content", "text", "markdown", "body")
    if not set(payload).issubset(set(content_keys) | metadata_keys):
        return ""
    return _first_string_value(payload, content_keys)


def _expand_escaped_whitespace(text: str) -> str:
    return text.replace("\\r", "\n").replace("\\n", "\n").replace("\\t", "\t")
