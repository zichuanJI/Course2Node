"""Minimax lightweight agent for the retrieve stage.
Runs a multi-turn tool-use loop with web_search to gather supplemental evidence.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings
from app.core.providers import RetrieveAgentProvider, SearchProvider

MINIMAX_CHAT_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"


class MinimaxRetrieveAgent(RetrieveAgentProvider):
    def __init__(self, search_provider: SearchProvider, model: str = "abab6.5-chat") -> None:
        self._search = search_provider
        self.model = model

    async def run_agent(
        self,
        task: str,
        context: str,
        max_turns: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Run a tool-use loop. Each turn the model may call web_search.
        Returns list of evidence dicts: {url, title, snippet, relevance}.
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "top_k": {"type": "integer", "default": 5},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research assistant helping to supplement lecture notes. "
                    "Use web_search to look up missing definitions, theorems, or context. "
                    "Only search for terms that appear ambiguous or undefined in the lecture. "
                    "Do not contradict lecture content."
                ),
            },
            {
                "role": "user",
                "content": f"Lecture context:\n{context}\n\nTask:\n{task}",
            },
        ]

        evidence: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(max_turns):
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                }
                headers = {
                    "Authorization": f"Bearer {settings.minimax_api_key}",
                    "Content-Type": "application/json",
                }
                resp = await client.post(MINIMAX_CHAT_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                choice = data["choices"][0]
                msg = choice["message"]
                messages.append(msg)

                if not msg.get("tool_calls"):
                    break

                for tool_call in msg["tool_calls"]:
                    if tool_call["function"]["name"] == "web_search":
                        args = json.loads(tool_call["function"]["arguments"])
                        results = await self._search.search(
                            args["query"], args.get("top_k", 5)
                        )
                        evidence.extend(results)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(results, ensure_ascii=False),
                        })

        return evidence
