"""Gemini 2.5 Pro adapter (flagship – alternative to Claude)."""
from __future__ import annotations

import json
from typing import Any

import google.generativeai as genai

from app.config import settings
from app.core.providers import LLMProvider


class GeminiLLMProvider(LLMProvider):
    def __init__(self, model: str = "gemini-2.5-pro") -> None:
        genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(model)
        self.model = model

    async def generate_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # Gemini supports response_mime_type=application/json with a schema
        generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        response = await self._model.generate_content_async(
            full_prompt,
            generation_config=generation_config,
        )
        return json.loads(response.text)
