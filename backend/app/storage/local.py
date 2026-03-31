"""Local disk artifact storage (dev mode)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.config import settings


def _root() -> Path:
    p = Path(settings.local_storage_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def artifact_path(session_id: uuid.UUID, stage: str, version: int, ext: str = "json") -> Path:
    """Returns the path where an artifact should be stored."""
    d = _root() / str(session_id) / stage
    d.mkdir(parents=True, exist_ok=True)
    return d / f"v{version}.{ext}"


def write_artifact(session_id: uuid.UUID, stage: str, version: int, data: dict) -> Path:
    path = artifact_path(session_id, stage, version)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    return path


def read_artifact(session_id: uuid.UUID, stage: str, version: int) -> dict:
    path = artifact_path(session_id, stage, version)
    return json.loads(path.read_text())


def write_upload(session_id: uuid.UUID, filename: str, data: bytes) -> Path:
    d = _root() / str(session_id) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    p.write_bytes(data)
    return p
