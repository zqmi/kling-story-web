"""旁白 TTS 异步任务：分镜 narration → Edge TTS → `project_audio` + job.result。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_generated_audio_dir, settings
from app.core.database import AsyncSessionLocal
from app.models.tables import AgentJob, ProjectAudio, ProjectStoryboard
from app.schemas.audio_job import TtsNarrationJobCreate
from app.schemas.outline import OutlineAgentJobResponse
from app.services.audio_store import upsert_project_audio
from app.services.tts_edge import synthesize_shot_narration

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_TTS = 2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_client_shots(raw: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            continue
        sid = str(s.get("shotId") or s.get("id") or "").strip() or f"sb-{i:03d}"
        idx = str(s.get("index") or "").strip() or f"{i + 1:02d}"
        text = str(s.get("text") or s.get("narration") or "").strip()
        out.append({"shotId": sid, "index": idx, "text": text})
    return out


def _shots_from_storyboard_body(body: dict[str, Any]) -> list[dict[str, str]]:
    panels = body.get("panels")
    if not isinstance(panels, list):
        return []
    out: list[dict[str, str]] = []
    for i, p in enumerate(panels):
        if not isinstance(p, dict):
            continue
        script = p.get("script") if isinstance(p.get("script"), dict) else {}
        narration = str(script.get("narration") or "").strip()
        sid = str(p.get("id") or "").strip() or f"sb-{i:03d}"
        idx = str(p.get("index") or "").strip() or f"{i + 1:02d}"
        out.append({"shotId": sid, "index": idx, "text": narration})
    return out


class TtsNarrationJobService:
    async def create_tts_narration_job(
        self,
        session: AsyncSession,
        body: TtsNarrationJobCreate,
    ) -> OutlineAgentJobResponse:
        pid = (body.projectId or "").strip() or "default"
        job_id = str(uuid.uuid4())
        shots_payload = body.shots if isinstance(body.shots, list) else None
        job = AgentJob(
            id=job_id,
            status="queued",
            payload={
                "type": "tts_narration",
                "projectId": pid,
                "voice": (body.voice or "").strip(),
                "shots": shots_payload,
            },
            result=None,
            finished_at=None,
        )
        session.add(job)
        await session.commit()
        asyncio.create_task(_run_tts_narration_job(job_id))
        return OutlineAgentJobResponse(jobId=job_id, status="queued")


tts_narration_job_service = TtsNarrationJobService()


async def _run_tts_narration_job(job_id: str) -> None:
    project_id = "default"
    voice_req = ""
    shots_override: list[Any] | None = None
    async with AsyncSessionLocal() as session:
        job = await session.get(AgentJob, job_id)
        if not job:
            return
        job.status = "running"
        payload = dict(job.payload or {})
        project_id = str(payload.get("projectId") or "default").strip() or "default"
        voice_req = str(payload.get("voice") or "").strip()
        raw_shots = payload.get("shots")
        shots_override = list(raw_shots) if isinstance(raw_shots, list) and len(raw_shots) > 0 else None
        await session.commit()

    voice = voice_req or settings.edge_tts_voice
    dest_root = get_generated_audio_dir()
    dest_root.mkdir(parents=True, exist_ok=True)

    try:
        if shots_override is not None:
            shots = _normalize_client_shots(shots_override)
        else:
            async with AsyncSessionLocal() as session:
                row = await session.get(ProjectStoryboard, project_id)
                if not row or not isinstance(row.body, dict):
                    raise RuntimeError("分镜不存在或为空，请先保存或生成分镜")
                shots = _shots_from_storyboard_body(row.body)

        to_synth = [s for s in shots if s.get("text")]
        if not to_synth:
            raise RuntimeError("没有可用的旁白文本（各镜 narration 均为空）")

        sem = asyncio.Semaphore(_MAX_CONCURRENT_TTS)

        async def _one(item: dict[str, str]) -> dict[str, Any]:
            base: dict[str, Any] = {
                "shotId": item["shotId"],
                "index": item["index"],
                "text": item["text"],
            }
            async with sem:
                try:
                    r = await synthesize_shot_narration(
                        text=item["text"],
                        voice=voice,
                        project_id=project_id,
                        shot_id=item["shotId"],
                        dest_root=dest_root,
                        url_prefix=settings.generated_audio_url_prefix,
                    )
                    return {**base, **r, "error": None}
                except Exception as e:
                    logger.warning("tts shot failed shotId=%s: %s", item.get("shotId"), e)
                    return {**base, "audioUrl": "", "durationMs": None, "error": str(e)}

        segments: list[dict[str, Any]] = await asyncio.gather(*[_one(x) for x in to_synth])

        body: dict[str, Any] = {"version": 1, "voice": voice, "segments": segments}

        async with AsyncSessionLocal() as session:
            row = await session.get(ProjectAudio, project_id)
            prev_ver = 1
            if row and isinstance(row.body, dict):
                try:
                    prev_ver = int(row.body.get("version") or 1)
                except (TypeError, ValueError):
                    prev_ver = 1
            body["version"] = prev_ver + 1 if row else 1
            await upsert_project_audio(session, project_id, body)
    except Exception as e:
        logger.exception("tts_narration job failed job_id=%s", job_id)
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
            "ttsRevisionId": job_id,
            "projectId": project_id,
            "tts": body,
            "source": "edge-tts",
            "segmentCount": len(body.get("segments") or []),
        }
        job.finished_at = _utc_now()
        await session.commit()
