"""Stage 3 – Align.
Monotonic transcript-to-slide alignment using embedding similarity
with order constraints (later chunk ↛ earlier slide).
"""
from __future__ import annotations

import uuid

from app.core.types import AlignedChunk, SlideUnit, TranscriptSegment


def run(session_id: uuid.UUID) -> None:
    """Entry point called by Celery task."""
    # TODO:
    #   1. Load transcript segments + slide units from extract artifact
    #   2. Chunk transcript into semantic windows
    #   3. Embed chunks + slides via EmbedProvider
    #   4. Run monotonic alignment (DTW or greedy similarity with order constraint)
    #   5. Write AlignArtifact to storage + DB
    print(f"[align] session={session_id} – stub, not yet implemented")


def chunk_transcript(segments: list[TranscriptSegment], window_sec: float = 60.0) -> list[list[TranscriptSegment]]:
    """Group consecutive segments into semantic windows."""
    raise NotImplementedError


def monotonic_align(
    chunk_embeddings: list[list[float]],
    slide_embeddings: list[list[float]],
    confidence_threshold: float = 0.5,
) -> list[AlignedChunk]:
    """
    Assign each transcript chunk to a primary slide index.
    Monotonicity: chunk[i].primary_slide_index >= chunk[i-1].primary_slide_index
    Chunks below confidence_threshold are flagged as uncertain.
    """
    raise NotImplementedError
