"""Tavily web search adapter."""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.core.providers import SearchProvider

TAVILY_URL = "https://api.tavily.com/search"


class TavilySearchProvider(SearchProvider):
    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                TAVILY_URL,
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "max_results": top_k,
                    "search_depth": "basic",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {"url": r["url"], "title": r.get("title", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])
        ]
