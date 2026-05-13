"""项目旁白 TTS 快照：读写 project_audio.body（version + voice + segments）。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import ProjectAudio


async def upsert_project_audio(session: AsyncSession, project_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = await session.get(ProjectAudio, project_id)
    if row:
        row.body = body
    else:
        session.add(ProjectAudio(project_id=project_id, body=body))
    await session.commit()
    return {"projectId": project_id, "ok": True}


async def get_project_audio(session: AsyncSession, project_id: str) -> dict[str, Any]:
    row = await session.get(ProjectAudio, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="audio not found for this project")
    return row.body
