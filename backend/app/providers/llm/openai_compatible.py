"""OpenAI-compatible chat adapter for graph extraction and lightweight vision fallback."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "",
        timeout_seconds: float = 60.0,
        max_output_tokens: int = 1200,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("package `openai` is required for OpenAI-compatible LLM access") from exc

        if not api_key or not model:
            raise RuntimeError("OpenAI-compatible provider requires both api_key and model")

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout_seconds,
            "max_retries": 0,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)
        self.model = model
        self.max_output_tokens = max_output_tokens

    def generate_json(
        self,
        *,
        prompt: str,
        system: str,
        temperature: float = 0.1,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        return self.generate_json_from_content(
            content=prompt,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    def generate_json_from_content(
        self,
        *,
        content: Any,
        system: str,
        temperature: float = 0.1,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        request = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_output_tokens or self.max_output_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        }
        try:
            response = self._client.chat.completions.create(
                **request,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            if _should_not_retry(exc):
                raise
            response = self._client.chat.completions.create(**request)
        content = _coerce_text(response.choices[0].message.content)
        return _parse_json_text(content)

    def generate_json_from_images(
        self,
        *,
        prompt: str,
        system: str,
        images: list[dict[str, str]],
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image["data_url"]},
                }
            )
        return self.generate_json_from_content(
            content=content,
            system=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    def extract_text_from_image(
        self,
        *,
        image_bytes: bytes,
        prompt: str,
        system: str,
        mime_type: str = "image/png",
        temperature: float = 0.0,
    ) -> str:
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=min(self.max_output_tokens, 1200),
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        return _coerce_text(response.choices[0].message.content).strip()

    def extract_file_content(self, file_path: str | Path, *, purpose: str = "file-extract") -> str:
        path = Path(file_path)
        file_object = self._client.files.create(file=path, purpose=purpose)
        file_id = file_object.id
        try:
            last_status = getattr(file_object, "status", "")
            for attempt in range(8):
                if attempt:
                    time.sleep(min(1.5 * attempt, 6.0))
                try:
                    content = self._client.files.content(file_id=file_id)
                    text = _coerce_file_content(content).strip()
                    if text:
                        return text
                except Exception as exc:
                    if attempt >= 7:
                        raise
                    last_status = str(exc)
                    continue

                try:
                    latest = self._client.files.retrieve(file_id=file_id)
                    last_status = getattr(latest, "status", last_status)
                    if str(last_status).lower() in {"failed", "error", "cancelled"}:
                        details = getattr(latest, "status_details", "")
                        raise RuntimeError(f"Kimi file extraction failed with status {last_status}: {details}")
                except Exception:
                    pass
            raise RuntimeError(f"Kimi file extraction returned empty content. Last status: {last_status}")
        finally:
            try:
                self._client.files.delete(file_id=file_id)
            except Exception:
                pass


def _coerce_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            text = getattr(item, "text", None)
            if text:
                parts.append(str(text))
                continue
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts)
    return str(content)


def _coerce_file_content(content: Any) -> str:
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    raw = getattr(content, "content", None)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return raw
    read = getattr(content, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        if isinstance(data, str):
            return data
    return _coerce_text(content)


def _parse_json_text(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {candidate[:400]}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Model JSON response must be an object")
    return payload


def _should_not_retry(exc: Exception) -> bool:
    name = exc.__class__.__name__
    message = str(exc).lower()
    if "timeout" in message:
        return True
    return name in {"APITimeoutError", "APIConnectionError", "RateLimitError", "AuthenticationError", "PermissionDeniedError"}
