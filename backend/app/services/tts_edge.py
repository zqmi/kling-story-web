"""Edge TTS：旁白合成到本地 mp3，返回相对 URL 与时长（毫秒）。"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _safe_segment(s: str, max_len: int = 128) -> str:
    t = re.sub(r"[^\w\-.]", "_", (s or "").strip()) or "x"
    return t[:max_len]


def _mp3_duration_ms(path: Path) -> int | None:
    try:
        from mutagen.mp3 import MP3  # type: ignore[import-untyped]

        audio = MP3(str(path))
        if audio.info is None or audio.info.length is None:
            return None
        return int(float(audio.info.length) * 1000)
    except Exception as e:
        logger.debug("mutagen duration skip: %s", e)
        return None


async def synthesize_edge_tts_to_mp3(
    text: str,
    *,
    out_path: Path,
    voice: str,
) -> None:
    """调用 edge-tts 写入 ``out_path``（.mp3）。"""
    try:
        import edge_tts  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError("未安装 edge-tts：请在 backend 执行 pip install edge-tts") from e

    t = (text or "").strip()
    if not t:
        raise ValueError("旁白文本为空")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(t, voice)
    await communicate.save(str(out_path))


def build_segment_audio_url(
    *,
    url_prefix: str,
    project_id: str,
    shot_id: str,
    filename: str,
) -> str:
    pfx = url_prefix.rstrip("/")
    sp = _safe_segment(str(project_id))
    sid = _safe_segment(str(shot_id))
    return f"{pfx}/{sp}/{sid}/{filename}"


async def synthesize_shot_narration(
    *,
    text: str,
    voice: str,
    project_id: str,
    shot_id: str,
    dest_root: Path,
    url_prefix: str,
) -> dict[str, Any]:
    """单镜旁白 → mp3；返回 segment 字段字典（含 audioUrl、durationMs）。"""
    sp = _safe_segment(str(project_id))
    sid = _safe_segment(str(shot_id))
    dest_dir = dest_root / sp / sid
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:14]}.mp3"
    out_path = dest_dir / name
    await synthesize_edge_tts_to_mp3(text, out_path=out_path, voice=voice)
    url = build_segment_audio_url(url_prefix=url_prefix, project_id=project_id, shot_id=shot_id, filename=name)
    dur = _mp3_duration_ms(out_path)
    return {"audioUrl": url, "durationMs": dur}
