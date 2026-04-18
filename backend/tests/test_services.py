from __future__ import annotations

import pytest

from app.core.types import (
    CourseSession,
    EvidenceChunk,
    GenerateNotesRequest,
    IngestArtifact,
    SessionStatus,
    SourceFile,
    SourceKind,
)
from app.services.graph_builder import build_graph
from app.services.ingestion import _extract_pdf_page_text, _transcribe_audio, ingest_source
from app.services.llm_graph import GraphExtractionResult, _select_graph_input_chunks
from app.services.notes import generate_notes
from app.services.search import search_graph
from app.config import settings
from app.storage.local import load_session, save_ingest_artifact, save_session


def test_build_graph_search_and_generate_notes_flow(tmp_storage):
    pdf_source = _make_source(SourceKind.pdf, "lecture.pdf")
    audio_source = _make_source(SourceKind.audio, "lecture.mp3")
    session = CourseSession(
        course_title="CS229",
        lecture_title="Linear Regression",
        source_files=[pdf_source, audio_source],
    )
    save_session(session)

    save_ingest_artifact(
        IngestArtifact(
            session_id=session.session_id,
            source_id=pdf_source.source_id,
            source_kind=SourceKind.pdf,
            chunks=[
                _make_chunk(
                    chunk_id=f"{pdf_source.source_id}-p1-1",
                    source_id=str(pdf_source.source_id),
                    source_type=SourceKind.pdf,
                    text="Linear regression models a target with weighted features. Gradient descent minimizes loss.",
                    page_start=1,
                    page_end=1,
                ),
                _make_chunk(
                    chunk_id=f"{pdf_source.source_id}-p1-2",
                    source_id=str(pdf_source.source_id),
                    source_type=SourceKind.pdf,
                    text="Gradient descent updates weights for linear regression by following the negative gradient.",
                    page_start=1,
                    page_end=1,
                ),
            ],
        )
    )
    save_ingest_artifact(
        IngestArtifact(
            session_id=session.session_id,
            source_id=audio_source.source_id,
            source_kind=SourceKind.audio,
            chunks=[
                _make_chunk(
                    chunk_id=f"{audio_source.source_id}-a1",
                    source_id=str(audio_source.source_id),
                    source_type=SourceKind.audio,
                    text="The lecture revisits linear regression and explains why gradient descent works in practice.",
                    time_start=0.0,
                    time_end=12.0,
                )
            ],
        )
    )

    graph = build_graph(session.session_id)

    assert graph.concepts
    assert graph.topic_clusters
    assert any("gradient" in concept.canonical_name for concept in graph.concepts)

    search = search_graph(session.session_id, "gradient descent", limit=5)
    assert search.concepts
    assert search.chunks
    assert search.concepts[0].score >= search.concepts[-1].score

    note = generate_notes(GenerateNotesRequest(session_id=session.session_id, topic="gradient descent"))

    assert note.sections
    assert note.summary
    assert note.sections[0].references

    stored_session = load_session(session.session_id)
    assert stored_session.status == SessionStatus.notes_ready
    assert stored_session.stats.chunk_count == 3
    assert stored_session.stats.concept_count == len(graph.concepts)


def test_build_graph_marks_session_failed_when_artifacts_are_missing(tmp_storage):
    session = CourseSession(course_title="CS229", lecture_title="Empty Lecture")
    save_session(session)

    with pytest.raises(ValueError, match="No ingest artifacts found"):
        build_graph(session.session_id)

    stored_session = load_session(session.session_id)
    assert stored_session.status == SessionStatus.failed
    assert "No ingest artifacts found" in (stored_session.error_message or "")


def test_ingest_source_marks_session_failed_when_pdf_ingestion_raises(tmp_storage, monkeypatch):
    import app.services.ingestion as ingestion_module

    source = _make_source(SourceKind.pdf, "broken.pdf")
    session = CourseSession(
        course_title="CS229",
        lecture_title="Broken Lecture",
        source_files=[source],
    )
    save_session(session)

    def raise_ingest_error(_source):
        raise RuntimeError("pdf parser exploded")

    monkeypatch.setattr(ingestion_module, "_ingest_pdf", raise_ingest_error)

    with pytest.raises(RuntimeError, match="pdf parser exploded"):
        ingest_source(session.session_id, source.source_id)

    stored_session = load_session(session.session_id)
    assert stored_session.status == SessionStatus.failed
    assert stored_session.error_message == "pdf parser exploded"


def test_transcribe_audio_returns_degraded_segment_when_all_backends_fail(tmp_storage, tmp_path, monkeypatch):
    import app.services.ingestion as ingestion_module

    audio_path = tmp_path / "lecture.mp3"
    audio_path.write_bytes(b"not-really-audio")

    def fail_with(message: str):
        def _fail(_audio_path):
            raise RuntimeError(message)

        return _fail

    monkeypatch.setattr(ingestion_module, "_transcribe_with_openai_whisper", fail_with("missing whisper"))
    monkeypatch.setattr(ingestion_module, "_transcribe_with_local_faster_whisper", fail_with("missing faster whisper"))
    monkeypatch.setattr(ingestion_module, "_transcribe_with_external_faster_whisper", fail_with("external runner down"))

    segments = _transcribe_audio(audio_path)

    assert len(segments) == 1
    assert segments[0]["start"] == 0.0
    assert "ASR failed for lecture.mp3" in str(segments[0]["text"])
    assert "missing whisper" in str(segments[0]["text"])


def test_build_graph_uses_llm_candidates_when_configured(tmp_storage, monkeypatch):
    import app.services.graph_builder as graph_builder_module

    source = _make_source(SourceKind.pdf, "lecture.pdf")
    session = CourseSession(
        course_title="CS229",
        lecture_title="Linear Regression",
        source_files=[source],
    )
    save_session(session)
    save_ingest_artifact(
        IngestArtifact(
            session_id=session.session_id,
            source_id=source.source_id,
            source_kind=SourceKind.pdf,
            chunks=[
                _make_chunk(
                    chunk_id=f"{source.source_id}-p1-1",
                    source_id=str(source.source_id),
                    source_type=SourceKind.pdf,
                    text="Linear regression uses gradient descent to minimize loss.",
                    page_start=1,
                    page_end=1,
                ),
                _make_chunk(
                    chunk_id=f"{source.source_id}-p2-1",
                    source_id=str(source.source_id),
                    source_type=SourceKind.pdf,
                    text="Gradient descent updates parameters according to the negative gradient.",
                    page_start=2,
                    page_end=2,
                ),
            ],
        )
    )

    monkeypatch.setattr(settings, "graph_llm_api_key", "demo-key")
    monkeypatch.setattr(settings, "graph_llm_model", "demo-model")
    monkeypatch.setattr(
        graph_builder_module,
        "extract_graph_candidates",
        lambda chunks: GraphExtractionResult.model_validate(
            {
                "concepts": [
                    {
                        "name": "Linear Regression",
                        "canonical_name": "linear regression",
                        "aliases": ["linear model"],
                        "definition": "A method that models a target with weighted features.",
                        "evidence_chunk_ids": [chunks[0].chunk_id],
                    },
                    {
                        "name": "Gradient Descent",
                        "canonical_name": "gradient descent",
                        "aliases": ["GD"],
                        "definition": "An optimization method that iteratively updates parameters.",
                        "evidence_chunk_ids": [chunks[0].chunk_id, chunks[1].chunk_id],
                    },
                ],
                "relations": [
                    {
                        "source_canonical_name": "gradient descent",
                        "target_canonical_name": "linear regression",
                        "edge_type": "RELATES_TO",
                        "relation_type": "used_for",
                        "evidence_chunk_ids": [chunks[0].chunk_id],
                        "confidence": 0.88,
                    }
                ],
            }
        ),
    )

    graph = build_graph(session.session_id)

    assert {concept.canonical_name for concept in graph.concepts} == {"linear regression", "gradient descent"}
    assert any(edge.properties.get("relation_type") == "used_for" for edge in graph.edges)
    assert len(graph.edges) == 1


def test_build_graph_fails_instead_of_silent_rule_fallback_when_llm_is_enabled(tmp_storage, monkeypatch):
    import app.services.graph_builder as graph_builder_module

    source = _make_source(SourceKind.pdf, "lecture.pdf")
    session = CourseSession(
        course_title="CS229",
        lecture_title="Linear Regression",
        source_files=[source],
    )
    save_session(session)
    save_ingest_artifact(
        IngestArtifact(
            session_id=session.session_id,
            source_id=source.source_id,
            source_kind=SourceKind.pdf,
            chunks=[
                _make_chunk(
                    chunk_id=f"{source.source_id}-p1-1",
                    source_id=str(source.source_id),
                    source_type=SourceKind.pdf,
                    text="Linear regression uses gradient descent to minimize loss.",
                    page_start=1,
                    page_end=1,
                )
            ],
        )
    )

    monkeypatch.setattr(settings, "graph_llm_api_key", "demo-key")
    monkeypatch.setattr(settings, "graph_llm_model", "demo-model")
    monkeypatch.setattr(settings, "graph_llm_strict", True)

    def explode(_chunks):
        raise RuntimeError("deepseek unavailable")

    monkeypatch.setattr(graph_builder_module, "extract_graph_candidates", explode)

    with pytest.raises(RuntimeError, match="LLM graph extraction failed: deepseek unavailable"):
        build_graph(session.session_id)

    stored_session = load_session(session.session_id)
    assert stored_session.status == SessionStatus.failed
    assert "LLM graph extraction failed: deepseek unavailable" in (stored_session.error_message or "")


def test_extract_pdf_page_text_uses_vision_fallback_for_sparse_pages(tmp_storage, monkeypatch):
    import app.services.ingestion as ingestion_module

    class FakePage:
        def get_text(self, _mode: str) -> str:
            return "12 13"

    monkeypatch.setattr(settings, "pdf_visual_fallback_min_chars", 80)
    monkeypatch.setattr(ingestion_module, "pdf_visual_fallback_configured", lambda: True)
    monkeypatch.setattr(
        ingestion_module,
        "_extract_pdf_page_with_vision",
        lambda page, page_index, filename: "Recovered slide bullet one. Recovered slide bullet two.",
    )

    page_text, used_fallback = _extract_pdf_page_text(FakePage(), 1, "slides.pdf", 0)

    assert used_fallback is True
    assert "Recovered slide bullet one" in page_text


def test_select_graph_input_chunks_limits_large_documents(tmp_storage, monkeypatch):
    monkeypatch.setattr(settings, "graph_llm_max_input_units", 14)

    chunks = [
        _make_chunk(
            chunk_id=f"chunk-{index}",
            source_id="demo-pdf",
            source_type=SourceKind.pdf,
            text=f"Page {index} explains linked lists, arrays, and complexity tradeoffs in detail.",
            page_start=index,
            page_end=index,
        )
        for index in range(1, 41)
    ]

    selected = _select_graph_input_chunks(chunks)

    assert len(selected) <= 14
    assert selected[0].page_start == 1
    assert selected[-1].page_start is not None


def _make_source(kind: SourceKind, filename: str) -> SourceFile:
    return SourceFile(
        kind=kind,
        filename=filename,
        content_type="application/pdf" if kind == SourceKind.pdf else "audio/mpeg",
        storage_path=f"/tmp/{filename}",
        size_bytes=1,
    )


def _make_chunk(
    chunk_id: str,
    source_id: str,
    source_type: SourceKind,
    text: str,
    page_start: int | None = None,
    page_end: int | None = None,
    time_start: float | None = None,
    time_end: float | None = None,
) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        source_type=source_type,
        text=text,
        summary=text,
        keywords=[],
        embedding=[],
        page_start=page_start,
        page_end=page_end,
        time_start=time_start,
        time_end=time_end,
    )
