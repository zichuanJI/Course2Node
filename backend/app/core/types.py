"""
Canonical data types for Course2Note.
All pipeline stages read and write these types.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SessionStatus(str, Enum):
    pending = "pending"
    ingesting = "ingesting"
    extracting = "extracting"
    aligning = "aligning"
    retrieving = "retrieving"
    synthesizing = "synthesizing"
    review = "review"
    done = "done"
    failed = "failed"


class SourceType(str, Enum):
    audio = "audio"
    slides = "slides"
    context_docs = "context_docs"
    web = "web"
    human_edit = "human_edit"


class NoteBlockKind(str, Enum):
    summary = "summary"
    section = "section"
    supplement = "supplement"
    term = "term"
    warning = "warning"
    question = "question"


class GroundingLevel(str, Enum):
    lecture = "lecture"
    supplemental = "supplemental"
    mixed = "mixed"


class ReviewAction(str, Enum):
    edit = "edit"
    accept = "accept"
    reject = "reject"
    rate = "rate"


class ExportFormat(str, Enum):
    markdown = "markdown"
    tex = "tex"
    txt = "txt"


# ---------------------------------------------------------------------------
# Source file record
# ---------------------------------------------------------------------------

class SourceFile(BaseModel):
    file_id: UUID = Field(default_factory=uuid4)
    filename: str
    content_type: str          # MIME type
    storage_path: str          # path in artifact store
    size_bytes: int
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Stage 1 – LectureSession
# ---------------------------------------------------------------------------

class LectureSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    course_title: str
    lecture_title: str
    language: str = "auto"    # "auto" | "zh" | "en"
    source_files: list[SourceFile] = []
    status: SessionStatus = SessionStatus.pending
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Stage 2 – Extract
# ---------------------------------------------------------------------------

class TranscriptSegment(BaseModel):
    segment_id: UUID = Field(default_factory=uuid4)
    start_sec: float
    end_sec: float
    text: str
    confidence: float = 1.0


class SlideUnit(BaseModel):
    index: int                        # 0-based slide/page number
    title: str = ""
    body_text: str = ""
    speaker_notes: str = ""
    ocr_text: str = ""                # populated only when OCR was used
    image_refs: list[str] = []        # storage paths for extracted images


# ---------------------------------------------------------------------------
# Stage 3 – Align
# ---------------------------------------------------------------------------

class AlignedChunk(BaseModel):
    chunk_id: UUID = Field(default_factory=uuid4)
    transcript_segment_ids: list[UUID]
    primary_slide_index: int | None   # None when no slide available
    candidate_slide_indexes: list[int] = []
    alignment_confidence: float = 1.0  # 0-1; below 0.5 → flagged uncertain


# ---------------------------------------------------------------------------
# Evidence & provenance
# ---------------------------------------------------------------------------

class EvidenceRef(BaseModel):
    source_type: SourceType
    source_id: str             # segment_id / slide index / file_id / url hash
    locator: str               # human-readable pointer ("slide 3", "00:42-01:05")
    url: str | None = None     # only for source_type=web


# ---------------------------------------------------------------------------
# Stage 5 – NoteDocument
# ---------------------------------------------------------------------------

class NoteBlock(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: NoteBlockKind
    title: str = ""
    content_md: str
    provenance: list[EvidenceRef] = []
    citations: list[EvidenceRef] = []
    grounding_level: GroundingLevel = GroundingLevel.lecture


class NoteSection(BaseModel):
    section_id: UUID = Field(default_factory=uuid4)
    title: str
    blocks: list[NoteBlock] = []
    slide_range: tuple[int, int] | None = None   # (first_slide, last_slide)


class NoteMetadata(BaseModel):
    session_id: UUID
    course_title: str
    lecture_title: str
    language: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    pipeline_version: str = "0.1.0"


class ExportMetadata(BaseModel):
    formats_available: list[ExportFormat] = []
    last_exported_at: datetime | None = None


class NoteDocument(BaseModel):
    metadata: NoteMetadata
    one_paragraph_summary: str = ""
    sections: list[NoteSection] = []
    supplemental_context: list[NoteBlock] = []
    key_terms: list[NoteBlock] = []
    open_questions: list[NoteBlock] = []
    export_metadata: ExportMetadata = Field(default_factory=ExportMetadata)


# ---------------------------------------------------------------------------
# Stage 6 – Review
# ---------------------------------------------------------------------------

class ReviewEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    note_block_id: UUID
    action: ReviewAction
    before: str | None = None      # markdown content before edit
    after: str | None = None       # markdown content after edit
    user_rating: int | None = None  # 1-5
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Pipeline artifact envelope
# Used to version-stamp every stage output written to disk / DB.
# ---------------------------------------------------------------------------

class PipelineArtifact(BaseModel):
    artifact_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    stage: str                      # "extract" | "align" | "retrieve" | "synthesize"
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    storage_path: str
    extra: dict[str, Any] = {}     # stage-specific metadata (prompt, model used, etc.)
