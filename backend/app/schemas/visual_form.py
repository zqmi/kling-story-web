"""分镜 paint → 描写页表单：请求/响应体。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class VisualFormFromPaintRequest(BaseModel):
    """单镜 panel（与导出 JSON 一致：id、index、script、paint 等）。"""

    panel: dict[str, Any] = Field(default_factory=dict)


class VisualFormFromPaintResponse(BaseModel):
    """描写页单条 `panels[]` 项形状（与前端 VisualView `createPanel` 对齐）。"""

    visualPanel: dict[str, Any]
    source: Literal["llm", "heuristic"] = "heuristic"
