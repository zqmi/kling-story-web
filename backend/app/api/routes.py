"""HTTP 路由。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.outline import OutlineAgentJobCreate, OutlineAgentJobResponse
from app.schemas.storyboard import StoryboardAgentJobCreate, StoryboardUpsert
from app.schemas.visual_form import VisualFormFromPaintRequest, VisualFormFromPaintResponse
from app.schemas.visual_panel_image import VisualPanelImageRequest
from app.schemas.audio_job import TtsNarrationJobCreate
from app.schemas.visual_job import VisualFromPromptsJobCreate, VisualUpsert
from app.services.outline_job_service import OutlineAgentJobService, outline_job_service
from app.services.audio_store import get_project_audio
from app.services.storyboard_job_service import StoryboardAgentJobService, storyboard_job_service
from app.services.storyboard_store import get_project_storyboard, upsert_project_storyboard
from app.services.tts_narration_job_service import TtsNarrationJobService, tts_narration_job_service
from app.services.visual_form_from_paint import visual_panel_from_storyboard_paint
from app.services.visual_job_service import VisualJobService, visual_job_service
from app.services.visual_panel_kling_image import generate_visual_panel_kling_image
from app.services.visual_store import get_project_visual, upsert_project_visual

router = APIRouter()


def get_outline_job_service() -> OutlineAgentJobService:
    return outline_job_service


def get_storyboard_job_service() -> StoryboardAgentJobService:
    return storyboard_job_service


def get_visual_job_service() -> VisualJobService:
    return visual_job_service


def get_tts_narration_job_service() -> TtsNarrationJobService:
    return tts_narration_job_service


@router.post("/api/audio/agent-jobs", response_model=OutlineAgentJobResponse)
async def create_tts_narration_agent_job(
    body: TtsNarrationJobCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    svc: TtsNarrationJobService = Depends(get_tts_narration_job_service),
) -> OutlineAgentJobResponse:
    """分镜叙述旁白 → Edge TTS（异步）；完成后写入 `project_audio` 与 `GET /api/jobs/:id` 的 result.tts。"""
    return await svc.create_tts_narration_job(session, body)


@router.get("/projects/{project_id}/audio")
async def get_project_audio_route(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """读取已存旁白 TTS 快照（version、voice、segments）。"""
    return await get_project_audio(session, project_id)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/outline/agent-jobs", response_model=OutlineAgentJobResponse)
async def create_outline_agent_job(
    body: OutlineAgentJobCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    svc: OutlineAgentJobService = Depends(get_outline_job_service),
) -> OutlineAgentJobResponse:
    return await svc.create_outline_agent_job(session, body)


@router.post("/api/visual/panel-image")
async def visual_panel_image(
    body: VisualPanelImageRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """单镜描写 → 拼主提示 → 可灵生图 → 下载到 `data/generated_visual/` → 合并 `localImagePaths` 到 `project_visuals`（若已有该镜）。"""
    return await generate_visual_panel_kling_image(session, body)


@router.post("/api/visual/agent-jobs", response_model=OutlineAgentJobResponse)
async def create_visual_from_prompts_agent_job(
    body: VisualFromPromptsJobCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    svc: VisualJobService = Depends(get_visual_job_service),
) -> OutlineAgentJobResponse:
    """全表主/负提示 + 旁白 → 画面描写（异步）；完成后写入 `project_visuals` 与 `GET /api/jobs/:id` 的 result.visual。"""
    return await svc.create_visual_from_prompts_job(session, body)


@router.post("/projects/{project_id}/visual")
async def upsert_visual(
    project_id: str,
    body: VisualUpsert,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """手动覆盖画面描写快照（version + panels）。"""
    return await upsert_project_visual(session, project_id, body.model_dump())


@router.get("/projects/{project_id}/visual")
async def get_visual(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """读取已存画面描写 body。"""
    return await get_project_visual(session, project_id)


@router.post("/api/storyboard/visual-form-from-paint", response_model=VisualFormFromPaintResponse)
async def storyboard_visual_form_from_paint(body: VisualFormFromPaintRequest) -> VisualFormFromPaintResponse:
    """将当前镜的绘画 API 字段（panel.paint + script）转成描写页单镜表单；无 API Key 时用规则兜底。"""
    visual_panel, source = await visual_panel_from_storyboard_paint(body.panel)
    return VisualFormFromPaintResponse(visualPanel=visual_panel, source=source)


@router.post("/api/storyboard/agent-jobs", response_model=OutlineAgentJobResponse)
async def create_storyboard_agent_job(
    body: StoryboardAgentJobCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    svc: StoryboardAgentJobService = Depends(get_storyboard_job_service),
) -> OutlineAgentJobResponse:
    """从大纲异步生成分镜：outline + LLM/占位 → `project_storyboards` + `GET /api/jobs` 的 result.storyboard。"""
    return await svc.create_storyboard_agent_job(session, body)


@router.get("/api/jobs/{job_id}")
async def get_job(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    svc: OutlineAgentJobService = Depends(get_outline_job_service),
) -> dict[str, Any]:
    return await svc.get_job(session, job_id)


@router.get("/projects/{project_id}/outline")
async def get_project_outline(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    svc: OutlineAgentJobService = Depends(get_outline_job_service),
) -> dict[str, Any]:
    return await svc.get_project_outline(session, project_id)


@router.post("/projects/{project_id}/storyboard")
async def upsert_storyboard(
    project_id: str,
    body: StoryboardUpsert,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """整表覆盖写入；与前端 `storyboardPayload()` 同形（version + panels）。"""
    return await upsert_project_storyboard(session, project_id, body.model_dump())


@router.get("/projects/{project_id}/storyboard")
async def get_storyboard(
    project_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """返回已存 body（version + panels）；无记录时 404。"""
    return await get_project_storyboard(session, project_id)
