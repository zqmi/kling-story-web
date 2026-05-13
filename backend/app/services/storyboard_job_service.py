"""分镜生成任务：AgentJob + 从请求中的大纲调用 LLM（或占位）生成 panels（script 以 narration 旁白为主），写入分镜库并写入 job.result。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tables import AgentJob
from app.schemas.outline import OutlineAgentJobResponse
from app.schemas.storyboard import StoryboardAgentJobCreate
from app.services.storyboard_graph import run_storyboard_linear_graph
from app.services.storyboard_store import upsert_project_storyboard

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clip(s: str, n: int) -> str:
    t = (s or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def outline_to_panels(outline: dict[str, Any], *, job_id: str) -> list[dict[str, Any]]:
    """将大纲 dict 转为与前端一致的 panel：`id`、`index`、可选 `trace`、`script`（仅 narration 旁白）、`paint`（占位展开）。"""
    synopsis = str(outline.get("synopsis") or "").strip()
    project = outline.get("project") if isinstance(outline.get("project"), dict) else {}
    logline = str(project.get("logline") or "").strip()
    title = str(project.get("title") or "").strip()
    acts_raw = outline.get("acts")
    panels: list[dict[str, Any]] = []

    def beat_to_panel(
        act_index: int,
        beat: dict[str, Any],
        act_name: str,
        act_goal: str,
        global_idx: int,
    ) -> dict[str, Any]:
        bid = str(beat.get("id") or "").strip()
        btype = str(beat.get("type") or "其他").strip()
        content = str(beat.get("content") or "").strip() or "（待补节拍）"
        bg_parts = [p for p in [act_name, act_goal] if p]
        narrative = " · ".join(bg_parts) if bg_parts else (synopsis or logline or "场景待定")
        ctx = _clip(f"{synopsis or logline}", 400)
        positive = _clip(
            f"{narrative}。节拍类型：{btype}。内容要点：{content}"
            + (f"。故事语境：{ctx}" if ctx else ""),
            900,
        )
        tags = ["分镜占位", btype] if btype else ["分镜占位"]
        if act_name:
            tags.append(act_name[:20])
        dlg = _clip(f"（占位旁白）{narrative}；{btype}：{content}", 200)
        return {
            "id": f"sb-{job_id[:8]}-{global_idx:03d}",
            "index": f"{global_idx:02d}",
            "trace": {"actIndex": act_index, "beatId": bid, "dialogueRef": ""},
            "script": {"dialogue": "", "narration": dlg},
            "paint": {
                "positivePrompt": positive,
                "negativePrompt": "低质量，畸形手指，多余肢体，文字水印，过度锐化",
                "styleTags": [t for t in tags if t][:12],
                "aspectRatio": "16:9",
                "continuity": "",
                "characterRefIds": [],
            },
        }

    if isinstance(acts_raw, list) and acts_raw:
        idx = 0
        for ai, act in enumerate(acts_raw):
            if not isinstance(act, dict):
                continue
            act_name = str(act.get("name") or act.get("title") or f"第 {ai + 1} 幕").strip()
            act_goal = str(act.get("dramaticGoal") or act.get("summary") or "").strip()
            beats = act.get("beats")
            if isinstance(beats, list) and beats:
                for beat in beats:
                    if not isinstance(beat, dict):
                        beat = {}
                    idx += 1
                    panels.append(beat_to_panel(ai, beat, act_name, act_goal, idx))
            else:
                idx += 1
                fake = {"id": "", "type": "其他", "content": act_goal or act_name or "（本幕无节拍）"}
                panels.append(beat_to_panel(ai, fake, act_name, act_goal, idx))

    if panels:
        return panels

    seed = " · ".join([p for p in [title, logline, synopsis] if p]) or "（尚无大纲内容，请先生成大纲）"
    return [
        {
            "id": f"sb-{job_id[:8]}-001",
            "index": "01",
            "trace": {"actIndex": 0, "beatId": "", "dialogueRef": ""},
            "script": {"dialogue": "", "narration": _clip(f"（占位旁白）{seed}", 200)},
            "paint": {
                "positivePrompt": _clip(seed, 900),
                "negativePrompt": "低质量，畸形手指，多余肢体，文字水印",
                "styleTags": ["分镜占位"],
                "aspectRatio": "16:9",
                "continuity": "",
                "characterRefIds": [],
            },
        }
    ]


class StoryboardAgentJobService:
    async def create_storyboard_agent_job(
        self,
        session: AsyncSession,
        body: StoryboardAgentJobCreate,
    ) -> OutlineAgentJobResponse:
        pid = (body.projectId or "").strip()
        if not pid:
            raise HTTPException(status_code=400, detail="projectId is required")
        job_id = str(uuid.uuid4())
        job = AgentJob(
            id=job_id,
            status="queued",
            payload={
                "type": "storyboard_agent",
                "projectId": pid,
                "outline": body.outline if isinstance(body.outline, dict) else {},
            },
            result=None,
            finished_at=None,
        )
        session.add(job)
        await session.commit()
        asyncio.create_task(_run_storyboard_agent_job(job_id))
        return OutlineAgentJobResponse(jobId=job_id, status="queued")


storyboard_job_service = StoryboardAgentJobService()


async def _run_storyboard_agent_job(job_id: str) -> None:
    project_id = "default"
    raw_outline: dict[str, Any] = {}
    async with AsyncSessionLocal() as session:
        job = await session.get(AgentJob, job_id)
        if not job:
            return
        job.status = "running"
        payload = dict(job.payload or {})
        project_id = str(payload.get("projectId") or "default").strip() or "default"
        o = payload.get("outline")
        raw_outline = dict(o) if isinstance(o, dict) else {}
        await session.commit()

    body: dict[str, Any] = {"version": 1, "panels": []}
    try:
        outline_only = dict(raw_outline)
        if not outline_only:
            raise RuntimeError("请求中未携带大纲 outline，无法生成分镜")

        if settings.deepseek_api_key:
            panels = await run_storyboard_linear_graph(outline_only, job_id=job_id)
        else:
            logger.warning("DEEPSEEK_API_KEY 未设置，分镜任务使用节拍占位展开（仅开发用）")
            panels = outline_to_panels(outline_only, job_id=job_id)

        if not panels:
            raise RuntimeError("生成的分镜 panels 为空")

        body = {"version": 1, "panels": panels}

        async with AsyncSessionLocal() as session:
            await upsert_project_storyboard(session, project_id, body)
    except Exception as e:
        logger.exception("storyboard agent failed job_id=%s", job_id)
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
            "storyboardRevisionId": job_id,
            "projectId": project_id,
            "storyboard": body,
            "panelCount": len(body.get("panels") or []),
        }
        job.finished_at = _utc_now()
        await session.commit()
