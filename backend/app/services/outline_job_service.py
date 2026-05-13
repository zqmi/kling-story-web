"""大纲 Agent 任务：PostgreSQL + DeepSeek 生成大纲。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.tables import AgentJob, ProjectOutline
from app.schemas.outline import OutlineAgentJobCreate, OutlineAgentJobResponse
from app.services.outline_langgraph import generate_outline_langgraph

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OutlineAgentJobService:
    async def create_outline_agent_job(
        self,
        session: AsyncSession,
        body: OutlineAgentJobCreate,
    ) -> OutlineAgentJobResponse:
        if not body.userDraft.strip():
            raise HTTPException(status_code=400, detail="userDraft is required")
        job_id = str(uuid.uuid4())
        job = AgentJob(
            id=job_id,
            status="queued",
            payload=body.model_dump(),
            result=None,
            finished_at=None,
        )
        session.add(job)
        await session.commit()
        asyncio.create_task(_run_outline_agent_job(job_id))
        return OutlineAgentJobResponse(jobId=job_id, status="queued")

    async def get_job(self, session: AsyncSession, job_id: str) -> dict[str, Any]:
        job = await session.get(AgentJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return {
            "jobId": job.id,
            "status": job.status,
            "created_at": job.created_at.isoformat().replace("+00:00", "Z") if job.created_at else None,
            "finished_at": job.finished_at.isoformat().replace("+00:00", "Z") if job.finished_at else None,
            "result": job.result,
        }

    async def get_project_outline(self, session: AsyncSession, project_id: str) -> dict[str, Any]:
        row = await session.get(ProjectOutline, project_id)
        if not row:
            raise HTTPException(status_code=404, detail="outline not found for this project")
        return row.body

outline_job_service = OutlineAgentJobService()

async def _run_outline_agent_job(job_id: str) -> None:
    """后台任务：独立 Session；调用 DeepSeek 写入大纲。"""
    payload_copy: dict[str, Any] = {}
    async with AsyncSessionLocal() as session:
        job = await session.get(AgentJob, job_id)
        if not job:
            return
        job.status = "running"
        payload_copy = dict(job.payload or {})
        await session.commit()

    try:
        outline_snapshot = await generate_outline_langgraph(payload_copy)
    except Exception as e:
        logger.exception("outline agent failed job_id=%s", job_id)
        async with AsyncSessionLocal() as session:
            job = await session.get(AgentJob, job_id)
            if job:
                job.status = "failed"
                job.result = {"error": str(e)}
                job.finished_at = _utc_now()
                await session.commit()
        return

    async with AsyncSessionLocal() as session:
        job = await session.get(AgentJob, job_id)
        if not job:
            return
        job.status = "succeeded"
        job.result = {"outlineRevisionId": job_id, "outline": outline_snapshot}
        job.finished_at = _utc_now()

        existing = await session.get(ProjectOutline, "default")
        if existing:
            existing.body = outline_snapshot
            existing.updated_at = _utc_now()
        else:
            session.add(ProjectOutline(project_id="default", body=outline_snapshot))
        await session.commit()
