"""ORM 表：任务、项目大纲快照、项目分镜快照。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentJob(Base):
    __tablename__ = "agent_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectOutline(Base):
    __tablename__ = "project_outlines"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProjectStoryboard(Base):
    __tablename__ = "project_storyboards"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProjectVisual(Base):
    """项目「画面描写」快照：与前端 VisualView `panels[]` 同形（version + panels）。"""

    __tablename__ = "project_visuals"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProjectAudio(Base):
    """项目旁白 TTS 快照：`version`、`voice`、`segments[]`（shotId、index、text、audioUrl、durationMs、error）。"""

    __tablename__ = "project_audio"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
