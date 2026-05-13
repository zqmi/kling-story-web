"""画面描写异步任务：请求体。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VisualFromPromptsJobCreate(BaseModel):
    """与前端 `shots[]` 一致：id、index、positivePrompt、negativePrompt、narration。"""

    projectId: str = "default"
    shots: list[dict[str, Any]] = Field(default_factory=list)


class VisualUpsert(BaseModel):
    """整表覆盖画面描写；与前端 VisualView `panels` 导出同形。"""

    version: int = 1
    panels: list[dict[str, Any]] = Field(default_factory=list)
    characterStyleAnchor: str = Field(
        default="",
        description="全镜共用的角色外观锚定（衣形、主色等），拼进每镜主提示前缀；与分镜再生描写时可由后端保留",
    )
