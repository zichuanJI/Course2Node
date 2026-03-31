"""
Celery task definitions – one task per pipeline stage.
Each task calls the corresponding pipeline module and writes artifacts.
"""
from __future__ import annotations

import uuid

from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="pipeline.run_full")
def run_full_pipeline(self, session_id: str) -> dict:
    """Orchestrate all stages sequentially for a session."""
    sid = uuid.UUID(session_id)
    self.update_state(state="STARTED", meta={"stage": "ingest"})

    from app.pipeline import ingest, extract, align, retrieve, synthesize

    ingest.run(sid)
    self.update_state(state="PROGRESS", meta={"stage": "extract"})

    extract.run(sid)
    self.update_state(state="PROGRESS", meta={"stage": "align"})

    align.run(sid)
    self.update_state(state="PROGRESS", meta={"stage": "retrieve"})

    retrieve.run(sid)
    self.update_state(state="PROGRESS", meta={"stage": "synthesize"})

    synthesize.run(sid)
    return {"session_id": session_id, "status": "done"}


@celery_app.task(name="pipeline.stage.ingest")
def task_ingest(session_id: str) -> None:
    from app.pipeline import ingest
    ingest.run(uuid.UUID(session_id))


@celery_app.task(name="pipeline.stage.extract")
def task_extract(session_id: str) -> None:
    from app.pipeline import extract
    extract.run(uuid.UUID(session_id))


@celery_app.task(name="pipeline.stage.align")
def task_align(session_id: str) -> None:
    from app.pipeline import align
    align.run(uuid.UUID(session_id))


@celery_app.task(name="pipeline.stage.retrieve")
def task_retrieve(session_id: str) -> None:
    from app.pipeline import retrieve
    retrieve.run(uuid.UUID(session_id))


@celery_app.task(name="pipeline.stage.synthesize")
def task_synthesize(session_id: str) -> None:
    from app.pipeline import synthesize
    synthesize.run(uuid.UUID(session_id))
