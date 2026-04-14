from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from app.config import settings
from app.core.types import CourseSession, EvidenceChunk, IngestArtifact, SessionStatus, SourceFile, SourceKind
from app.services.text_utils import extract_candidate_terms, hash_embedding, split_text, summarize_text
from app.storage.local import load_session, save_ingest_artifact, save_session


def ingest_source(session_id: uuid.UUID, source_id: uuid.UUID) -> IngestArtifact:
    session = load_session(session_id)
    source = _find_source(session, source_id)
    session.status = SessionStatus.ingesting
    save_session(session)

    if source.kind == SourceKind.pdf:
        chunks = _ingest_pdf(source)
    elif source.kind == SourceKind.audio:
        chunks = _ingest_audio(source)
    else:
        raise ValueError(f"Unsupported source kind: {source.kind}")

    artifact = IngestArtifact(
        session_id=session_id,
        source_id=source_id,
        source_kind=source.kind,
        chunks=chunks,
    )
    path = save_ingest_artifact(artifact)

    source.ingested = True
    source.ingest_artifact_path = str(path)
    session.status = SessionStatus.uploaded
    session.updated_at = artifact.created_at
    save_session(session)
    return artifact


def _find_source(session: CourseSession, source_id: uuid.UUID) -> SourceFile:
    for source in session.source_files:
        if source.source_id == source_id:
            return source
    raise ValueError(f"Source {source_id} not found in session {session.session_id}")


def _ingest_pdf(source: SourceFile) -> list[EvidenceChunk]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF ingestion.") from exc

    document = fitz.open(source.storage_path)
    chunks: list[EvidenceChunk] = []
    for page_index, page in enumerate(document, start=1):
        page_text = page.get_text("text")
        for local_index, piece in enumerate(split_text(page_text), start=1):
            if not piece.strip():
                continue
            chunk_id = f"{source.source_id}-p{page_index}-{local_index}"
            chunks.append(
                EvidenceChunk(
                    chunk_id=chunk_id,
                    source_id=str(source.source_id),
                    source_type=SourceKind.pdf,
                    text=piece,
                    summary=summarize_text(piece),
                    keywords=extract_candidate_terms(piece),
                    embedding=hash_embedding(piece),
                    page_start=page_index,
                    page_end=page_index,
                )
            )
    return chunks


def _ingest_audio(source: SourceFile) -> list[EvidenceChunk]:
    segments = _transcribe_audio(Path(source.storage_path))
    chunks: list[EvidenceChunk] = []
    for index, segment in enumerate(segments, start=1):
        text = segment["text"].strip()
        if not text:
            continue
        chunks.append(
            EvidenceChunk(
                chunk_id=f"{source.source_id}-a{index}",
                source_id=str(source.source_id),
                source_type=SourceKind.audio,
                text=text,
                summary=summarize_text(text),
                keywords=extract_candidate_terms(text),
                embedding=hash_embedding(text),
                time_start=segment["start"],
                time_end=segment["end"],
            )
        )
    return chunks


def _transcribe_audio(audio_path: Path) -> list[dict[str, float | str]]:
    failures: list[str] = []

    try:
        return _transcribe_with_openai_whisper(audio_path)
    except Exception as exc:
        failures.append(f"openai-whisper unavailable: {exc}")

    try:
        return _transcribe_with_local_faster_whisper(audio_path)
    except Exception as exc:
        failures.append(f"local faster-whisper unavailable: {exc}")

    try:
        return _transcribe_with_external_faster_whisper(audio_path)
    except Exception as exc:
        failures.append(f"external faster-whisper failed: {exc}")

    message = " | ".join(failures) if failures else "unknown ASR failure"
    return [{
        "start": 0.0,
        "end": 0.0,
        "text": f"ASR failed for {audio_path.name}: {message}",
    }]


def _transcribe_with_openai_whisper(audio_path: Path) -> list[dict[str, float | str]]:
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        raise RuntimeError("package `whisper` not installed") from exc

    wav_path = _convert_audio_for_asr(audio_path)
    try:
        model = whisper.load_model(settings.whisper_model_size)
        result = model.transcribe(
            str(wav_path),
            fp16=False,
            language=None if settings.whisper_language == "auto" else settings.whisper_language,
        )
        segments = result.get("segments") or []
        if segments:
            return [
                {
                    "start": float(segment.get("start", 0.0)),
                    "end": float(segment.get("end", 0.0)),
                    "text": str(segment.get("text", "")).strip(),
                }
                for segment in segments
            ]
        text = str(result.get("text", "")).strip()
        return [{"start": 0.0, "end": 0.0, "text": text}]
    finally:
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)


def _transcribe_with_local_faster_whisper(audio_path: Path) -> list[dict[str, float | str]]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise RuntimeError("package `faster_whisper` not installed") from exc

    wav_path = _convert_audio_for_asr(audio_path)
    try:
        model = WhisperModel(settings.whisper_model_size, device="auto", compute_type="default")
        segments_iter, _info = model.transcribe(
            str(wav_path),
            language=None if settings.whisper_language == "auto" else settings.whisper_language,
            vad_filter=True,
            beam_size=5,
            word_timestamps=False,
        )
        return [
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
            }
            for segment in segments_iter
            if segment.text.strip()
        ]
    finally:
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)


def _transcribe_with_external_faster_whisper(audio_path: Path) -> list[dict[str, float | str]]:
    python_path = Path(settings.faster_whisper_python_path)
    runner_path = Path(settings.faster_whisper_runner_path)
    if not python_path.exists():
        raise RuntimeError(f"missing python at {python_path}")
    if not runner_path.exists():
        raise RuntimeError(f"missing runner at {runner_path}")

    wav_path = _convert_audio_for_asr(audio_path)
    with tempfile.NamedTemporaryFile(prefix="course2node_asr_", suffix=".json", delete=False) as handle:
        output_path = Path(handle.name)

    try:
        command = [
            str(python_path),
            str(runner_path),
            "--audio",
            str(wav_path),
            "--output",
            str(output_path),
            "--model",
            settings.whisper_model_size,
            "--language",
            settings.whisper_language,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(stderr or "external faster-whisper returned non-zero exit status")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        return payload.get("segments", [])
    finally:
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def _convert_audio_for_asr(audio_path: Path) -> Path:
    fd, tmp_path = tempfile.mkstemp(prefix="course2node_audio_", suffix=".wav")
    os.close(fd)
    target = Path(tmp_path)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        target.unlink(missing_ok=True)
        raise RuntimeError(stderr or "ffmpeg conversion failed")
    return target
