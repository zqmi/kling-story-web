"""项目分镜表：读写 project_storyboards.body。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import ProjectStoryboard


async def upsert_project_storyboard(
    session: AsyncSession,
    project_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    row = await session.get(ProjectStoryboard, project_id)
    if row:
        row.body = body
    else:
        session.add(ProjectStoryboard(project_id=project_id, body=body))
    await session.commit()
    return {"projectId": project_id, "ok": True}


async def get_project_storyboard(session: AsyncSession, project_id: str) -> dict[str, Any]:
    row = await session.get(ProjectStoryboard, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="storyboard not found for this project")
    return row.body
