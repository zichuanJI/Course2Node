from __future__ import annotations

import json

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
from app.services.ingestion import _transcribe_audio, ingest_source
from app.services.llm_graph import (
    GraphExtractionResult,
    _build_graph_prompt,
    _extract_batch_candidates,
    _looks_like_noise,
    _looks_like_truncated_json_error,
    _select_graph_input_chunks,
)
from app.services.kimi_pdf import ExtractedPdfTextBlock, split_kimi_file_content
from app.services.notes import generate_notes
from app.services.search import search_graph
from app.config import settings
from app.storage.local import load_session, save_ingest_artifact, save_session


def test_build_graph_search_and_generate_notes_flow(tmp_storage, monkeypatch):
    import app.services.notes as notes_module

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
                ),
                _make_chunk(
                    chunk_id=f"{pdf_source.source_id}-p1-2",
                    source_id=str(pdf_source.source_id),
                    source_type=SourceKind.pdf,
                    text="Gradient descent updates weights for linear regression by following the negative gradient.",
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

    monkeypatch.setattr(
        notes_module,
        "_generate_note_with_llm",
        lambda graph, lecture_title, topic="": notes_module.LLMNoteDocument.model_validate(
            {
                "title": "Linear Regression - 图谱笔记",
                "summary": "围绕线性回归和梯度下降生成的学习笔记。",
                "sections": [
                    {
                        "title": "线性回归与优化",
                        "content_md": "线性回归使用加权特征建模目标值，梯度下降用于最小化损失。",
                        "concept_ids": [graph.concepts[0].concept_id],
                    }
                ],
            }
        ),
    )

    note = generate_notes(GenerateNotesRequest(session_id=session.session_id))

    assert note.sections
    assert note.summary
    assert note.sections[0].references == []
    assert note.topic == "当前知识图谱"

    stored_session = load_session(session.session_id)
    assert stored_session.status == SessionStatus.notes_ready
    assert stored_session.stats.chunk_count == 3
    assert stored_session.stats.concept_count == len(graph.concepts)


def test_generate_notes_requires_graph_llm_when_not_mocked(tmp_storage, monkeypatch):
    source = _make_source(SourceKind.pdf, "lecture.pdf")
    session = CourseSession(course_title="CS229", lecture_title="Linear Regression", source_files=[source])
    save_session(session)
    save_ingest_artifact(
        IngestArtifact(
            session_id=session.session_id,
            source_id=source.source_id,
            source_kind=SourceKind.pdf,
            chunks=[
                _make_chunk(
                    chunk_id=f"{source.source_id}-d1-1",
                    source_id=str(source.source_id),
                    source_type=SourceKind.pdf,
                    text="Linear regression uses gradient descent to minimize loss.",
                )
            ],
        )
    )
    graph = build_graph(session.session_id)
    assert graph.concepts

    monkeypatch.setattr(settings, "graph_llm_api_key", "")
    monkeypatch.setattr(settings, "graph_llm_model", "")

    with pytest.raises(RuntimeError, match="Notes LLM is not configured"):
        generate_notes(GenerateNotesRequest(session_id=session.session_id))


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


def test_transcribe_audio_raises_when_all_backends_fail(tmp_storage, tmp_path, monkeypatch):
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

    with pytest.raises(RuntimeError, match="ASR failed for lecture.mp3") as exc_info:
        _transcribe_audio(audio_path)

    assert "missing whisper" in str(exc_info.value)


def test_build_graph_rejects_asr_failure_chunks_before_llm(tmp_storage):
    audio_source = _make_source(SourceKind.audio, "lecture.mp3")
    session = CourseSession(
        course_title="CS229",
        lecture_title="Broken Audio",
        source_files=[audio_source],
    )
    save_session(session)
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
                    text="ASR failed for lecture.mp3: package `whisper` not installed",
                    time_start=0.0,
                    time_end=0.0,
                )
            ],
        )
    )

    with pytest.raises(RuntimeError, match="Audio transcription failed before graph extraction"):
        build_graph(session.session_id)

    stored_session = load_session(session.session_id)
    assert stored_session.status == SessionStatus.failed
    assert "Audio transcription failed before graph extraction" in (stored_session.error_message or "")


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
                ),
                _make_chunk(
                    chunk_id=f"{source.source_id}-p2-1",
                    source_id=str(source.source_id),
                    source_type=SourceKind.pdf,
                    text="Gradient descent updates parameters according to the negative gradient.",
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
                    },
                    {
                        "name": "Gradient Descent",
                        "canonical_name": "gradient descent",
                        "aliases": ["GD"],
                        "definition": "An optimization method that iteratively updates parameters.",
                    },
                ],
                "relations": [
                    {
                        "source_canonical_name": "gradient descent",
                        "target_canonical_name": "linear regression",
                        "edge_type": "RELATES_TO",
                        "relation_type": "used_for",
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


def test_ingest_pdf_uses_kimi_file_extraction_and_real_embedding_hook(tmp_storage, monkeypatch):
    import app.services.ingestion as ingestion_module

    source = _make_source(SourceKind.pdf, "slides.pdf")
    source.storage_path = str(tmp_storage / "slides.pdf")
    (tmp_storage / "slides.pdf").write_bytes(b"%PDF-1.4 fake")
    session = CourseSession(
        course_title="CS229",
        lecture_title="Slides",
        source_files=[source],
    )
    save_session(session)

    monkeypatch.setattr(
        ingestion_module,
        "kimi_pdf_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        ingestion_module,
        "embedding_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        ingestion_module,
        "extract_pdf_text_with_kimi",
        lambda filename, path: [
            ExtractedPdfTextBlock(
                page_index=1,
                text="Linked lists and recursion on page 1.\n- Definition\n- Complexity",
            ),
            ExtractedPdfTextBlock(
                page_index=2,
                text="Stacks use push and pop operations on page 2.",
            ),
        ],
    )

    artifact = ingest_source(session.session_id, source.source_id)

    assert artifact.chunks
    assert all(chunk.embedding for chunk in artifact.chunks)
    assert artifact.chunks[0].page_start is None
    assert "-d1-" in artifact.chunks[0].chunk_id
    assert "Linked lists and recursion" in artifact.chunks[0].text


def test_split_kimi_file_content_unwraps_json_content_with_page_markers():
    payload = json.dumps(
        {
            "content": "第 1 页\n线性回归介绍。\n第 2 页\n梯度下降更新权重。",
        },
        ensure_ascii=False,
    )

    blocks = split_kimi_file_content(payload)

    assert [block.page_index for block in blocks] == [None, None]
    assert "线性回归介绍" in blocks[0].text
    assert not blocks[0].text.startswith("{")


def test_split_kimi_file_content_reads_structured_page_objects():
    payload = json.dumps(
        {
            "pages": [
                {"page": 3, "title": "回归诊断", "content": "残差图用于检查模型假设。"},
                {"page_index": 4, "body_text": "多重共线性会导致系数不稳定。", "bullets": ["VIF 可用于检测"]},
            ]
        },
        ensure_ascii=False,
    )

    blocks = split_kimi_file_content(payload)

    assert [block.page_index for block in blocks] == [None, None]
    assert "残差图" in blocks[0].text
    assert "VIF" in blocks[1].text


def test_select_graph_input_chunks_keeps_all_valid_chunks_by_default(tmp_storage, monkeypatch):
    monkeypatch.setattr(settings, "graph_llm_max_input_units", 0)

    chunks = [
        _make_chunk(
            chunk_id=f"chunk-{index}",
            source_id="demo-pdf",
            source_type=SourceKind.pdf,
            text=f"Page {index} explains linked lists, arrays, and complexity tradeoffs in detail.",
        )
        for index in range(1, 41)
    ]

    selected = _select_graph_input_chunks(chunks)

    assert len(selected) == len(chunks)
    assert selected[0].chunk_id == "chunk-1"
    assert selected[-1].chunk_id == "chunk-40"


def test_graph_prompt_includes_curation_rules(tmp_storage):
    chunk = _make_chunk(
        chunk_id="chunk-1",
        source_id="demo-pdf",
        source_type=SourceKind.pdf,
        text="关系模型包含关系、域、笛卡尔积、候选码、主码和外码等核心概念。",
    )

    prompt = _build_graph_prompt([chunk])

    assert "候选概念 -> 噪声剔除 -> 同义归一化" in prompt
    assert "默认丢弃人名、学号、课程号、专业号" in prompt
    assert "关系模型、关系、域、笛卡尔积" in prompt
    assert "definition 必须是一句教学定义" in prompt
    assert "尽量完整抽取" in prompt
    assert "key_points 最多 3 条" in prompt
    assert "不要输出 evidence_chunk_ids" in prompt


def test_graph_noise_filter_uses_curation_rules(tmp_storage):
    assert _looks_like_noise("第二章")
    assert _looks_like_noise("2.1.1")
    assert _looks_like_noise("学号")
    assert _looks_like_noise("张清玫")
    assert _looks_like_noise("关系数据结构及形式化定义")
    assert not _looks_like_noise("关系模型")


def test_truncated_json_error_is_retryable(tmp_storage):
    error = ValueError('Model did not return valid JSON: { "concepts": [ { "name": "相关分析", "ap')
    assert _looks_like_truncated_json_error(error)
    assert not _looks_like_truncated_json_error(ValueError("Graph provider unavailable"))


def test_truncated_batch_is_split_before_compact_retry(tmp_storage, monkeypatch):
    chunks = [
        _make_chunk(
            chunk_id=f"chunk-{index}",
            source_id="demo-pdf",
            source_type=SourceKind.pdf,
            text=f"Concept {index} has a definition and a teaching explanation.",
        )
        for index in range(1, 3)
    ]
    calls: list[str] = []

    class FakeProvider:
        def generate_json(self, *, prompt: str, system: str, max_output_tokens: int | None = None, temperature: float = 0.1):
            calls.append(prompt)
            if len(calls) == 1:
                raise ValueError('Model did not return valid JSON: { "concepts": [')
            chunk_id = "chunk-2" if "Concept 2" in prompt else "chunk-1"
            return {
                "concepts": [
                    {
                        "name": chunk_id,
                        "canonical_name": chunk_id,
                        "definition": "A test concept.",
                    }
                ],
                "relations": [],
            }

    results = _extract_batch_candidates(FakeProvider(), chunks)  # type: ignore[arg-type]

    assert len(calls) == 3
    assert len(results) == 2
    assert {result.concepts[0].name for result in results} == {"chunk-1", "chunk-2"}


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
