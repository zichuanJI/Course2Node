"""SQLAlchemy ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LectureSessionORM(Base):
    __tablename__ = "lecture_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_title: Mapped[str] = mapped_column(String(512))
    lecture_title: Mapped[str] = mapped_column(String(512))
    language: Mapped[str] = mapped_column(String(16), default="auto")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    source_files: Mapped[dict] = mapped_column(JSONB, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    artifacts: Mapped[list[PipelineArtifactORM]] = relationship(back_populates="session", cascade="all, delete-orphan")
    review_events: Mapped[list[ReviewEventORM]] = relationship(back_populates="session", cascade="all, delete-orphan")


class PipelineArtifactORM(Base):
    __tablename__ = "pipeline_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lecture_sessions.id"))
    stage: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    storage_path: Mapped[str] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[LectureSessionORM] = relationship(back_populates="artifacts")


class ReviewEventORM(Base):
    __tablename__ = "review_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lecture_sessions.id"))
    note_block_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(32))
    before: Mapped[str | None] = mapped_column(Text, nullable=True)
    after: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[LectureSessionORM] = relationship(back_populates="review_events")
