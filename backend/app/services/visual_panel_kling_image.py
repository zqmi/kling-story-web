"""单镜描写 → 拼接主提示 → 可灵文生图 → 本地下载 → 合并进 project_visuals。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.kling_config import get_kling_config
from app.integrations.kling_image_client import KlingImageClient, KlingImageError
from app.schemas.visual_panel_image import VisualPanelImageRequest
from app.services.visual_image_download import download_kling_images_to_local
from app.services.visual_paint_prompt import build_visual_positive_prompt_from_panel
from app.services.visual_store import merge_local_image_paths_into_visual_panel


async def generate_visual_panel_kling_image(
    session: AsyncSession,
    body: VisualPanelImageRequest,
) -> dict[str, Any]:
    panel_dict: dict[str, Any] = body.panel.model_dump()
    raw_figs = panel_dict.get("figures") or []
    figs: list[dict[str, str]] = []
    for i in range(2):
        if i < len(raw_figs) and isinstance(raw_figs[i], dict):
            f = raw_figs[i]
            figs.append(
                {
                    "role": str(f.get("role") or "").strip(),
                    "costume": str(f.get("costume") or "").strip(),
                    "action": str(f.get("action") or "").strip(),
                }
            )
        else:
            figs.append({"role": "", "costume": "", "action": ""})
    panel_dict["figures"] = figs

    prompt = build_visual_positive_prompt_from_panel(
        panel_dict,
        character_style_anchor=body.characterStyleAnchor,
    )
    if not prompt.strip():
        raise HTTPException(
            status_code=400,
            detail="无法从描写字段生成有效主提示，请补充场景、人物或勾选手动主提示并填写 directPrompt",
        )

    neg = str(panel_dict.get("negativeShort") or "").strip() or None

    cfg = get_kling_config()
    client = KlingImageClient(cfg)
    if not client.configured():
        raise HTTPException(
            status_code=503,
            detail="未配置可灵鉴权：请设置 KLING_ACCESS_KEY + KLING_SECRET_KEY，或 KLING_API_KEY",
        )

    try:
        result = await client.generate(
            prompt,
            n=body.n,
            aspect_ratio=(body.aspectRatio or "16:9").strip() or "16:9",
            resolution=(body.resolution or "1k").strip() or "1k",
            negative_prompt=neg,
        )
    except KlingImageError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    local_paths = await download_kling_images_to_local(
        result.urls,
        project_id=body.projectId,
        panel_id=panel_dict.get("id"),
    )

    saved = await merge_local_image_paths_into_visual_panel(
        session,
        body.projectId,
        panel_dict.get("id"),
        local_paths,
        character_style_anchor=body.characterStyleAnchor,
    )

    return {
        "projectId": body.projectId,
        "panelId": panel_dict.get("id"),
        "promptUsed": prompt,
        "negativePromptUsed": neg or "",
        "urls": result.urls,
        "sourceUrls": result.urls,
        "localImagePaths": local_paths,
        "persistedToVisual": saved,
        "taskId": result.task_id,
        "modelName": result.model_name,
    }
