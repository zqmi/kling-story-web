"""集中读环境变量；database 等模块从这里取配置。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 无论从仓库根目录还是 backend 目录启动，都加载 backend/.env（再允许 CWD 下的 .env 覆盖）
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def get_backend_dir() -> Path:
    """`backend/` 根目录（内含 `app/`、`data/`）。"""
    return _BACKEND_DIR


load_dotenv(_BACKEND_DIR / ".env")
load_dotenv()


class Settings:
    app_title: str = "kling-story-api"
    app_version: str = "0.1.0"
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/kling_story",
    )
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]
    # DeepSeek（OpenAI 兼容）：https://api.deepseek.com
    deepseek_api_key: str = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    deepseek_base_url: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    deepseek_model: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    # 可灵（Kling）文生图：与 kling-story-pipeline-local story_agent 环境变量对齐
    kling_api_base: str = os.environ.get("KLING_API_BASE", "https://api-beijing.klingai.com").rstrip("/")
    kling_access_key: str = os.environ.get("KLING_ACCESS_KEY", "").strip()
    kling_secret_key: str = os.environ.get("KLING_SECRET_KEY", "").strip()
    kling_api_key: str = os.environ.get("KLING_API_KEY", "").strip()
    kling_jwt_ttl_seconds: int = int(os.environ.get("KLING_JWT_TTL_SECONDS", "1800"))
    kling_image_model_name: str = os.environ.get("KLING_IMAGE_MODEL_NAME", "kling-v1").strip() or "kling-v1"
    kling_image_generations_path: str = (
        os.environ.get("KLING_IMAGE_GENERATIONS_PATH", "/v1/images/generations").strip() or "/v1/images/generations"
    )
    kling_image_tasks_path_prefix: str = (
        os.environ.get("KLING_IMAGE_TASKS_PATH_PREFIX", "/v1/images/generations").strip()
        or "/v1/images/generations"
    )
    kling_image_model_field: str = os.environ.get("KLING_IMAGE_MODEL_FIELD", "model").strip().lower() or "model"
    kling_http_timeout_seconds: float = float(os.environ.get("KLING_HTTP_TIMEOUT_SECONDS", "120"))
    kling_poll_interval_seconds: float = float(os.environ.get("KLING_POLL_INTERVAL_SECONDS", "2"))
    kling_poll_max_seconds: float = float(os.environ.get("KLING_POLL_MAX_SECONDS", "300"))

    # 本地下载的可灵生图：`backend/data/generated_visual/`，经 `GET {prefix}/...` 访问
    generated_visual_url_prefix: str = (
        os.environ.get("GENERATED_VISUAL_URL_PREFIX", "/media/generated-visual").strip()
        or "/media/generated-visual"
    )

    # Edge TTS 旁白 mp3：`backend/data/generated_audio/`
    generated_audio_url_prefix: str = (
        os.environ.get("GENERATED_AUDIO_URL_PREFIX", "/media/generated-audio").strip()
        or "/media/generated-audio"
    )
    edge_tts_voice: str = (
        os.environ.get("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural").strip() or "zh-CN-XiaoxiaoNeural"
    )


settings = Settings()


def get_generated_visual_dir() -> Path:
    """可灵生图本地下载目录：`backend/data/generated_visual/`。"""
    return _BACKEND_DIR / "data" / "generated_visual"


def get_generated_audio_dir() -> Path:
    """旁白 TTS 输出目录：`backend/data/generated_audio/`。"""
    return _BACKEND_DIR / "data" / "generated_audio"
