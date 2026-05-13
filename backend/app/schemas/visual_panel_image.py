"""POST /api/visual/panel-image 请求体：与前端 `buildPanelPayloadForImageApi` 字段名一致（camelCase）。"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field


class VisualPanelFigureIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str = ""
    costume: str = ""
    action: str = ""


class VisualPanelPayloadIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Union[int, str]
    title: str = ""
    scenePlace: str = ""
    sceneTimeWeather: str = ""
    sceneProps: str = ""
    figures: list[VisualPanelFigureIn] = Field(default_factory=list)
    shotScale: str = ""
    cameraAngle: str = ""
    dof: str = ""
    lighting: str = ""
    colorMood: str = ""
    negativeShort: str = ""
    useDirectPrompt: bool = False
    directPrompt: str = ""


class VisualPanelImageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projectId: str = "default"
    panel: VisualPanelPayloadIn
    characterStyleAnchor: str = ""
    aspectRatio: str = "16:9"
    resolution: str = "1k"
    n: int = Field(default=1, ge=1, le=4)
