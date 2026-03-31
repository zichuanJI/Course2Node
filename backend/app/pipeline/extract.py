"""Stage 2 – Extract.
- Audio → timestamped TranscriptSegment[] via ASR
- PPTX  → SlideUnit[] (title, body, notes, images)
- PDF   → SlideUnit[] (text extraction; OCR fallback)
- Context docs → reference blocks
"""
from __future__ import annotations

import uuid

from app.core.types import SlideUnit, TranscriptSegment


def run(session_id: uuid.UUID) -> None:
    """Entry point called by Celery task."""
    # TODO:
    #   1. Load source files from storage
    #   2. Dispatch ASR / PPTX / PDF / context-doc extractors
    #   3. Write ExtractArtifact to storage + DB
    print(f"[extract] session={session_id} – stub, not yet implemented")


def extract_audio(audio_path: str) -> list[TranscriptSegment]:
    """Run ASR on audio file, return timestamped segments."""
    raise NotImplementedError


def extract_pptx(pptx_path: str) -> list[SlideUnit]:
    """Parse PPTX, return one SlideUnit per slide."""
    raise NotImplementedError


def extract_pdf(pdf_path: str) -> list[SlideUnit]:
    """Extract text from PDF; fall back to OCR for image-heavy pages."""
    raise NotImplementedError
