"""将描写页单镜 dict 拼成与前端 VisualView `buildPaintPrompt` 一致的主提示（送可灵 `prompt`）。"""

from __future__ import annotations

from typing import Any

_MAX_PROMPT_CHARS = 4500


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _anchor_prefix(character_style_anchor: str | None) -> str:
    a = _norm(character_style_anchor)
    if not a:
        return ""
    return f"【外观一致·全镜共用】{a}；"


def build_visual_positive_prompt_from_panel(
    panel: dict[str, Any],
    *,
    character_style_anchor: str | None = None,
) -> str:
    """与 `VisualView.vue` 中 `buildPaintPrompt` 顺序与分隔符一致；可选全镜外观锚定前缀。"""
    prefix = _anchor_prefix(character_style_anchor)
    use_dp = bool(panel.get("useDirectPrompt"))
    direct = _norm(panel.get("directPrompt"))
    if use_dp and direct:
        out = f"{prefix}{direct}" if prefix else direct
    else:
        parts: list[str] = []
        figures = panel.get("figures")
        if not isinstance(figures, list):
            figures = []
        for f in figures:
            if not isinstance(f, dict):
                continue
            role = _norm(f.get("role"))
            costume = _norm(f.get("costume"))
            action = _norm(f.get("action"))
            if not costume and not action and not role:
                continue
            label = f"{role}：" if role and role != "—" else ""
            body = "，".join(x for x in (costume, action) if x)
            if body:
                parts.append(f"{label}{body}")

        place = _norm(panel.get("scenePlace"))
        tw = _norm(panel.get("sceneTimeWeather"))
        props = _norm(panel.get("sceneProps"))
        setting_bits = [x for x in (place, tw, props) if x]
        if setting_bits:
            parts.append(f"场景：{'，'.join(setting_bits)}")

        lighting = _norm(panel.get("lighting"))
        color_mood = _norm(panel.get("colorMood"))
        light_bits = [x for x in (lighting, color_mood) if x]
        if light_bits:
            parts.append(f"光色：{'；'.join(light_bits)}")

        cam_bits = [
            x
            for x in (
                _norm(panel.get("shotScale")),
                _norm(panel.get("cameraAngle")),
                _norm(panel.get("dof")),
            )
            if x
        ]
        if cam_bits:
            parts.append(f"镜头：{'，'.join(cam_bits)}")

        core = "；".join(parts) if parts else ""
        out = f"{prefix}{core}" if prefix and core else (prefix or core)

    if not out.strip():
        return ""
    if len(out) > _MAX_PROMPT_CHARS:
        return out[: _MAX_PROMPT_CHARS - 1].rstrip() + "…"
    return out
