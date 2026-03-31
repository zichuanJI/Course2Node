"""
Abstract provider interfaces.
Concrete adapters live in app/providers/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Flagship LLM for extract / synthesize stages."""

    @abstractmethod
    async def generate_structured(
        self,
        schema: dict[str, Any],
        prompt: str,
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Generate a response that conforms to `schema` (JSON Schema).
        Returns the parsed dict.
        """
        ...


class RetrieveAgentProvider(ABC):
    """Lightweight agent (e.g. Minimax) for the retrieve stage.
    Runs multi-turn tool-use loops with web search.
    """

    @abstractmethod
    async def run_agent(
        self,
        task: str,
        context: str,
        max_turns: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Execute an agentic loop.
        Returns a list of evidence dicts:
          {"url": str, "title": str, "snippet": str, "relevance": float}
        """
        ...


class SearchProvider(ABC):
    """Web search backend."""

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Returns list of: {"url": str, "title": str, "snippet": str}
        """
        ...


class EmbedProvider(ABC):
    """Text embedding backend for the align stage."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Returns one embedding vector per input text."""
        ...


class ExportRenderer(ABC):
    """Renders a NoteDocument to a target format."""

    @abstractmethod
    def render(self, note_document: dict[str, Any], fmt: str) -> str:
        """
        fmt: "markdown" | "tex" | "txt"
        Returns rendered string.
        """
        ...
