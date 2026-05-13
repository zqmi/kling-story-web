"""可灵图像 API 配置：从 app.core.config.settings 读取（与 pipeline story_agent 环境变量对齐）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class KlingConfig:
    kling_api_base: str
    kling_access_key: str
    kling_secret_key: str
    kling_api_key: str
    kling_jwt_ttl_seconds: int
    kling_image_model_name: str
    kling_image_generations_path: str
    kling_image_tasks_path_prefix: str
    kling_image_model_field: str
    kling_http_timeout_seconds: float
    kling_poll_interval_seconds: float
    kling_poll_max_seconds: float


def get_kling_config() -> KlingConfig:
    mf = (settings.kling_image_model_field or "model").lower()
    model_field = "model_name" if mf == "model_name" else "model"
    return KlingConfig(
        kling_api_base=settings.kling_api_base.rstrip("/"),
        kling_access_key=settings.kling_access_key,
        kling_secret_key=settings.kling_secret_key,
        kling_api_key=settings.kling_api_key,
        kling_jwt_ttl_seconds=settings.kling_jwt_ttl_seconds,
        kling_image_model_name=settings.kling_image_model_name.strip() or "kling-v1",
        kling_image_generations_path=settings.kling_image_generations_path or "/v1/images/generations",
        kling_image_tasks_path_prefix=settings.kling_image_tasks_path_prefix.rstrip("/")
        or "/v1/images/generations",
        kling_image_model_field=model_field,
        kling_http_timeout_seconds=settings.kling_http_timeout_seconds,
        kling_poll_interval_seconds=settings.kling_poll_interval_seconds,
        kling_poll_max_seconds=settings.kling_poll_max_seconds,
    )
