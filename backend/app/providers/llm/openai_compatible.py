"""OpenAI-compatible chat adapter for graph extraction and lightweight vision fallback."""
from __future__ import annotations

import base64
import json
from typing import Any


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "",
        timeout_seconds: float = 60.0,
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

    def generate_json(
        self,
        *,
        prompt: str,
        system: str,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        request = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            response = self._client.chat.completions.create(
                **request,
                response_format={"type": "json_object"},
            )
        except Exception:
            response = self._client.chat.completions.create(**request)
        content = _coerce_text(response.choices[0].message.content)
        return _parse_json_text(content)

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
