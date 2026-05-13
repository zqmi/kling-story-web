"""分镜表写入体：与前端 `panels[]` 导出 JSON 对齐。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StoryboardUpsert(BaseModel):
    """整表快照；panels 为结构化列表，具体字段由前后端约定。"""

    version: int = 1
    panels: list[dict[str, Any]] = Field(default_factory=list)


class StoryboardAgentJobCreate(BaseModel):
    """从大纲异步生成分镜：与大纲页当前结构化字段对齐（project / synopsis / acts / anchors）。"""

    projectId: str = "default"
    outline: dict[str, Any] = Field(default_factory=dict)
