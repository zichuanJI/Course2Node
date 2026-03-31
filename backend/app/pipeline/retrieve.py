"""Stage 4 – Retrieve.
Uses a lightweight Minimax Agent (tool-use loop) to search the web
and collect supplemental EvidenceRef items.
Retrieval is OPTIONAL and only fires for specific knowledge gaps.
"""
from __future__ import annotations

import uuid

from app.core.types import EvidenceRef, SourceType


RETRIEVAL_TRIGGERS = [
    "term_definition_gap",
    "theorem_background",
    "acronym_disambiguation",
    "low_confidence_fact",
]


def run(session_id: uuid.UUID) -> None:
    """Entry point called by Celery task."""
    # TODO:
    #   1. Load align artifact; identify low-confidence chunks + unknown terms
    #   2. Generate search queries via Minimax Agent
    #   3. Agent runs tool-use loop (web_search calls) to gather evidence
    #   4. Tag each result as source_type=web, build EvidenceRef[]
    #   5. Write RetrieveArtifact (queries, raw results, evidence refs) to storage + DB
    print(f"[retrieve] session={session_id} – stub, not yet implemented")


def build_queries(
    lecture_title: str,
    slide_headings: list[str],
    low_confidence_texts: list[str],
) -> list[str]:
    """Generate web search queries from lecture signals."""
    raise NotImplementedError


def evidence_from_result(result: dict) -> EvidenceRef:
    """Convert a search hit dict into an EvidenceRef."""
    return EvidenceRef(
        source_type=SourceType.web,
        source_id=result["url"],
        locator=result.get("title", ""),
        url=result["url"],
    )
