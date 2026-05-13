"""将可灵返回的图片 URL 下载到 `backend/data/generated_visual/` 并生成可经 StaticFiles 访问的路径。"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_generated_visual_dir, settings

logger = logging.getLogger(__name__)

_EXT_FROM_CT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _safe_segment(s: str, max_len: int = 128) -> str:
    t = re.sub(r"[^\w\-.]", "_", (s or "").strip()) or "x"
    return t[:max_len]


def _guess_ext(content_type: str | None, url: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _EXT_FROM_CT:
        return _EXT_FROM_CT[ct]
    path = urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"


async def download_kling_images_to_local(
    urls: list[str],
    *,
    project_id: str,
    panel_id: Any,
) -> list[str]:
    """下载远程图到本地，返回浏览器可用的路径列表（以 `settings.generated_visual_url_prefix` 开头）。"""
    root = get_generated_visual_dir()
    root.mkdir(parents=True, exist_ok=True)
    prefix = settings.generated_visual_url_prefix.rstrip("/")
    sp = _safe_segment(str(project_id))
    sid = _safe_segment(str(panel_id))
    dest_dir = root / sp / sid
    dest_dir.mkdir(parents=True, exist_ok=True)

    out: list[str] = []
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        for i, url in enumerate(urls):
            u = (url or "").strip()
            if not u.startswith(("http://", "https://")):
                continue
            try:
                resp = await client.get(u)
                if resp.status_code >= 400:
                    logger.warning("download image failed status=%s url=%s", resp.status_code, u[:120])
                    continue
                ext = _guess_ext(resp.headers.get("content-type"), u)
                name = f"{uuid.uuid4().hex[:14]}_{i}{ext}"
                path = dest_dir / name
                path.write_bytes(resp.content)
                rel = f"{prefix}/{sp}/{sid}/{name}"
                out.append(rel)
            except Exception as e:
                logger.warning("download image exception: %s url=%s", e, u[:120])
                continue
    return out
