"""旁白 TTS 异步任务：请求体。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TtsNarrationJobCreate(BaseModel):
    """从分镜叙述旁白批量合成语音；不传 `shots` 时由服务端读 `project_storyboards`。"""

    projectId: str = "default"
    voice: str = Field(
        default="",
        description="Edge TTS 音色名，如 zh-CN-XiaoxiaoNeural；空则用环境变量默认值",
    )
    shots: list[dict[str, Any]] | None = Field(
        default=None,
        description="可选；每项含 shotId、index、text（旁白）。空或 None 则从分镜库读取",
    )
