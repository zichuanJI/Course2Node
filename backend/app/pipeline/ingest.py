"""Stage 1 – Ingest.
Validate uploaded files and update session status.
File bytes are already written by the upload API; this stage just sanity-checks them.
"""
from __future__ import annotations

import uuid

from app.core.types import SessionStatus


def run(session_id: uuid.UUID) -> None:
    """Entry point called by Celery task."""
    # TODO: validate files, detect language hint, update session status → extracting
    print(f"[ingest] session={session_id} – stub, not yet implemented")
