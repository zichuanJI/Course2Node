"""Stage 5 – Synthesize.
Uses a flagship LLM (Claude Opus 4 / Sonnet 4.6 or Gemini 2.5 Pro)
to produce a canonical NoteDocument JSON from aligned transcript + slides + web evidence.
"""
from __future__ import annotations

import uuid

from app.core.types import NoteDocument


SYSTEM_PROMPT = """\
You are an expert lecture note-taker. Your task is to produce a structured,
faithful set of notes from the provided lecture transcript and slides.

Rules:
- Follow the instructor's order and terminology precisely.
- Every claim must be traceable to the transcript (audio) or slides.
- Web evidence (source_type=web) may only appear in supplemental_context blocks,
  never in lecture-grounded sections.
- When evidence is sparse or conflicting, create a NoteBlock with kind=warning.
- Output valid JSON matching the NoteDocument schema exactly.
"""


def run(session_id: uuid.UUID) -> None:
    """Entry point called by Celery task."""
    # TODO:
    #   1. Load align artifact + retrieve artifact
    #   2. Build prompt from AlignedChunks + SlideUnits + EvidenceRefs
    #   3. Call LLMProvider.generate_structured(NoteDocument.model_json_schema(), prompt)
    #   4. Validate output against NoteDocument schema
    #   5. Write SynthesizeArtifact (prompt, raw output, parsed NoteDocument) to storage + DB
    #   6. Update session status → review
    print(f"[synthesize] session={session_id} – stub, not yet implemented")


def build_synthesis_prompt(
    aligned_chunks: list[dict],
    slide_units: list[dict],
    evidence_refs: list[dict],
) -> str:
    """Assemble the user prompt for the flagship LLM."""
    raise NotImplementedError
