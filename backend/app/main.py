"""FastAPI 应用：中间件、生命周期、路由。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_generated_audio_dir, get_generated_visual_dir, settings
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    import app.models  # noqa: F401 — 注册 ORM 到 Base.metadata

    get_generated_visual_dir().mkdir(parents=True, exist_ok=True)
    get_generated_audio_dir().mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_title, version=settings.app_version, lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    gen_dir = get_generated_visual_dir()
    gen_dir.mkdir(parents=True, exist_ok=True)
    application.mount(
        settings.generated_visual_url_prefix,
        StaticFiles(directory=str(gen_dir)),
        name="generated_visual",
    )
    audio_dir = get_generated_audio_dir()
    audio_dir.mkdir(parents=True, exist_ok=True)
    application.mount(
        settings.generated_audio_url_prefix,
        StaticFiles(directory=str(audio_dir)),
        name="generated_audio",
    )
    return application


app = create_app()
