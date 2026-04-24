"""OpenAI embedding adapter."""
from __future__ import annotations

from openai import OpenAI

from app.config import settings
from app.core.providers import EmbedProvider  # type: ignore


class OpenAIEmbedProvider(EmbedProvider):
    def __init__(self, model: str = "text-embedding-3-small", timeout_seconds: float = 30.0) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=timeout_seconds, max_retries=0)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]
