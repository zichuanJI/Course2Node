"""Claude Opus 4 / Sonnet 4.6 adapter (flagship – used for synthesize stage)."""
from __future__ import annotations

import json
from typing import Any

import anthropic

from app.config import settings
from app.core.providers import LLMProvider


class ClaudeLLMProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = model

    async def generate_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        tool_def = {
            "name": "output_structured",
            "description": "Output the result in the required JSON schema.",
            "input_schema": schema,
        }
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system or "You are a helpful assistant. Use the output_structured tool to respond.",
            messages=[{"role": "user", "content": prompt}],
            tools=[tool_def],
            tool_choice={"type": "tool", "name": "output_structured"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "output_structured":
                return block.input
        raise ValueError("Claude did not return a tool_use block")
