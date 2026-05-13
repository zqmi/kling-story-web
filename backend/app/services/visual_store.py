"""项目画面描写表：读写 project_visuals.body。"""

from __future__ import annotations

import copy
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import ProjectVisual


async def upsert_project_visual(
    session: AsyncSession,
    project_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    row = await session.get(ProjectVisual, project_id)
    if row:
        row.body = body
    else:
        session.add(ProjectVisual(project_id=project_id, body=body))
    await session.commit()
    return {"projectId": project_id, "ok": True}


async def get_project_visual(session: AsyncSession, project_id: str) -> dict[str, Any]:
    row = await session.get(ProjectVisual, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="visual not found for this project")
    return row.body


async def merge_local_image_paths_into_visual_panel(
    session: AsyncSession,
    project_id: str,
    panel_id: Any,
    new_paths: list[str],
    *,
    character_style_anchor: str | None = None,
) -> bool:
    """合并本镜 `localImagePaths`；可选写入全镜 `characterStyleAnchor`。

    `character_style_anchor` 非 ``None`` 时与库内比对，不同则更新（含清空为 ``""``）。
    """
    row = await session.get(ProjectVisual, project_id)
    if not row or not isinstance(row.body, dict):
        return False
    body = copy.deepcopy(row.body)
    changed = False

    if character_style_anchor is not None:
        av = str(character_style_anchor).strip()
        old = body.get("characterStyleAnchor")
        old_s = old.strip() if isinstance(old, str) else ""
        if old_s != av:
            body["characterStyleAnchor"] = av
            changed = True

    if new_paths:
        panels = body.get("panels")
        if not isinstance(panels, list):
            if not changed:
                return False
        else:
            pid = str(panel_id).strip()
            path_changed = False
            for i, p in enumerate(panels):
                if not isinstance(p, dict):
                    continue
                if str(p.get("id")).strip() != pid:
                    continue
                merged = dict(p)
                existing = merged.get("localImagePaths")
                if not isinstance(existing, list):
                    existing = []
                merged["localImagePaths"] = [
                    *existing,
                    *[x for x in new_paths if isinstance(x, str) and x.strip()],
                ]
                panels[i] = merged
                path_changed = True
                break
            if path_changed:
                body["panels"] = panels
                changed = True
            elif not changed:
                return False

    if not changed:
        return False
    row.body = body
    flag_modified(row, "body")
    await session.commit()
    return True
