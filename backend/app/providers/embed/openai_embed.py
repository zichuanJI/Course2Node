"""OpenAI embedding adapter (used in align stage)."""
from __future__ import annotations

from openai import AsyncOpenAI

from app.config import settings
from app.core.providers import EmbedProvider


class OpenAIEmbedProvider(EmbedProvider):
    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self.model,
            input=texts,
        )
        return [item.embedding for item in response.data]
