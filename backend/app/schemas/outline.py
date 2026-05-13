"""与前端 JSON 字段一致的 Pydantic 模型。"""

from pydantic import BaseModel, Field


class ProjectPayload(BaseModel):
    title: str = ""
    subtitle: str = ""
    logline: str = ""
    tags: list[str] = Field(default_factory=list)
    format: str = ""
    scope: str = ""
    productionNote: str = ""
    synopsisNote: str = ""


class OutlineAgentJobCreate(BaseModel):
    type: str = "outline_agent"
    userDraft: str
    project: ProjectPayload


class OutlineAgentJobResponse(BaseModel):
    jobId: str
    status: str
