"""画面描写异步任务：主/负提示 + 旁白 → LLM/规则生成 `panels`，写入 project_visuals + job.result。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.tables import AgentJob, ProjectVisual
from app.schemas.outline import OutlineAgentJobResponse
from app.schemas.visual_job import VisualFromPromptsJobCreate
from app.services.visual_store import upsert_project_visual
from app.services.visual_forms_from_prompts import visual_forms_from_prompts_batch

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VisualJobService:
    async def create_visual_from_prompts_job(
        self,
        session: AsyncSession,
        body: VisualFromPromptsJobCreate,
    ) -> OutlineAgentJobResponse:
        pid = (body.projectId or "").strip()
        if not pid:
            raise HTTPException(status_code=400, detail="projectId is required")
        shots = body.shots if isinstance(body.shots, list) else []
        if not shots:
            raise HTTPException(status_code=400, detail="shots 不能为空")
        job_id = str(uuid.uuid4())
        job = AgentJob(
            id=job_id,
            status="queued",
            payload={
                "type": "visual_from_prompts",
                "projectId": pid,
                "shots": shots,
            },
            result=None,
            finished_at=None,
        )
        session.add(job)
        await session.commit()
        asyncio.create_task(_run_visual_from_prompts_job(job_id))
        return OutlineAgentJobResponse(jobId=job_id, status="queued")


visual_job_service = VisualJobService()


async def _run_visual_from_prompts_job(job_id: str) -> None:
    project_id = "default"
    shots: list[dict[str, Any]] = []
    async with AsyncSessionLocal() as session:
        job = await session.get(AgentJob, job_id)
        if not job:
            return
        job.status = "running"
        payload = dict(job.payload or {})
        project_id = str(payload.get("projectId") or "default").strip() or "default"
        raw = payload.get("shots")
        shots = list(raw) if isinstance(raw, list) else []
        await session.commit()

    body: dict[str, Any] = {"version": 1, "panels": []}
    source = "heuristic"
    try:
        panels, source, character_style_anchor = await visual_forms_from_prompts_batch(shots)
        if not panels:
            raise RuntimeError("生成的描写 panels 为空")
        body = {
            "version": 1,
            "panels": panels,
            "characterStyleAnchor": (character_style_anchor or "").strip(),
        }

        async with AsyncSessionLocal() as session:
            row = await session.get(ProjectVisual, project_id)
            prev_ver = 1
            if row and isinstance(row.body, dict):
                try:
                    prev_ver = int(row.body.get("version") or 1)
                except (TypeError, ValueError):
                    prev_ver = 1
            body["version"] = prev_ver + 1 if row else 1
            await upsert_project_visual(session, project_id, body)
    except Exception as e:
        logger.exception("visual_from_prompts job failed job_id=%s", job_id)
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
        job.result = {
            "visualRevisionId": job_id,
            "projectId": project_id,
            "visual": body,
            "source": source,
            "panelCount": len(body.get("panels") or []),
        }
        job.finished_at = _utc_now()
        await session.commit()
