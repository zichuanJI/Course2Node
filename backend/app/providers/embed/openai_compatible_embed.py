"""OpenAI-compatible embedding adapter."""
from __future__ import annotations

from openai import OpenAI

from app.core.providers import EmbedProvider


class OpenAICompatibleEmbedProvider(EmbedProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key or not model:
            raise RuntimeError("OpenAI-compatible embedding provider requires both api_key and model")

        kwargs = {
            "api_key": api_key,
            "timeout": timeout_seconds,
            "max_retries": 0,
        }
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]
