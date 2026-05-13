"""将分镜单镜的绘画 API 字段（paint + script）规范为「描写页」结构化表单。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.storyboard_llm import _compose_positive_from_prompt_blocks, _norm_str

logger = logging.getLogger(__name__)

_SHOT_SCALES = ("特写", "中近景", "中景", "中全景", "全景", "大远景")
_CAMERA_ANGLES = ("平视", "略俯", "略仰", "顶视", "低机位")

_SYS_LLM = """你是影视分镜助理。输入为 JSON：`panel`（分镜单镜，含 `id`、`index`、`script.narration`、`paint` 等）。

请根据 **paint**（含 `promptBlocks` 六键、`positivePrompt`、`negativePrompt`、`continuity`、`styleTags`、`characterRefIds`、`aspectRatio`）与 **script.narration**，生成「描写页」使用的**单镜表单**。

只输出一个 JSON 对象（不要 markdown、不要解释），且**仅包含**下列键（不可增删键名）：
{
  "id": "字符串，沿用输入 panel.id",
  "title": "字符串，如 镜 01，与 panel.index 对应",
  "scenePlace": "地点/空间，短句",
  "sceneTimeWeather": "时间与天气或空字符串",
  "sceneProps": "关键陈设/道具或空字符串",
  "figures": [
    {"role": "", "costume": "", "action": ""},
    {"role": "", "costume": "", "action": ""}
  ],
  "shotScale": "必须是之一：特写、中近景、中景、中全景、全景、大远景",
  "cameraAngle": "必须是之一：平视、略俯、略仰、顶视、低机位",
  "dof": "景深/构图，可空",
  "lighting": "主光/照明描述，可空",
  "colorMood": "色调与氛围；若有 paint.continuity，可压缩并入此句前缀「连贯：」",
  "negativeShort": "从 negativePrompt 压缩为短排除项，逗号分隔即可",
  "useDirectPrompt": false,
  "directPrompt": "若 positivePrompt 已是很完整的一条绘画指令且难以拆字段，可置为与之一致的字符串并把 useDirectPrompt 置 true；否则置 \"\" 且 useDirectPrompt false"
}

规则：
- `figures` 必须**恰好两个**对象。**空镜、纯环境、无人物主体** 时两个对象三键均可为 `""`，禁止硬编路人。仅当 paint / narration 明确有可画主体时再填角色 1；有第二主体再填角色 2。
- **`costume`（服饰要点）**：先从 `positivePrompt`、各 `promptBlocks` 与 `narration` 里**收集**所有穿戴相关碎片（发型可见段、帽鞋袜包、领袖形制与色差、叠穿、首饰眼镜、污渍淋湿、布料褶皱反光），写入 `costume`，避免主提示已写明却漏写。**禁止**在仍有线索时只用「服装类型 + 单点状态」一行打发（反例：仅「校服，袖口湿」而别处还有领口配饰裤脚等）。**至少**两三处互不重复的可视信息；原文极短则在不编造新款前提下补裁剪裁影与布料状态。**大环境光与脸庞柔光**以 `lighting`/`colorMood` 为主，`costume` 最多半句写布料与肤色的受光交界，避免整段重复。走位手势表情只写在 `action`。
- 不要编造与 narration / paint 矛盾的内容。
- shotScale、cameraAngle 必须严格取自允许列表；无法判断时用「中景」「平视」。"""


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型输出中未找到 JSON 对象")
    return json.loads(t[start : end + 1])


def _coerce_enum(val: str, allowed: tuple[str, ...], default: str) -> str:
    v = _norm_str(val)
    if v in allowed:
        return v
    for a in allowed:
        if a in v:
            return a
    return default


def _empty_figure() -> dict[str, str]:
    return {"role": "", "costume": "", "action": ""}


def _normalize_visual_panel(raw: dict[str, Any], *, fallback_id: str, fallback_index: str) -> dict[str, Any]:
    pid = _norm_str(raw.get("id")) or fallback_id
    title = _norm_str(raw.get("title")) or f"镜 {fallback_index}"
    figs_in = raw.get("figures")
    figures: list[dict[str, str]] = []
    if isinstance(figs_in, list):
        for it in figs_in[:2]:
            if isinstance(it, dict):
                figures.append(
                    {
                        "role": _norm_str(it.get("role")),
                        "costume": _norm_str(it.get("costume")),
                        "action": _norm_str(it.get("action")),
                    }
                )
    while len(figures) < 2:
        figures.append(_empty_figure())

    use_dp = bool(raw.get("useDirectPrompt"))
    direct = _norm_str(raw.get("directPrompt"))

    return {
        "id": pid,
        "title": title,
        "scenePlace": _norm_str(raw.get("scenePlace")),
        "sceneTimeWeather": _norm_str(raw.get("sceneTimeWeather")),
        "sceneProps": _norm_str(raw.get("sceneProps")),
        "figures": figures[:2],
        "shotScale": _coerce_enum(_norm_str(raw.get("shotScale")), _SHOT_SCALES, "中景"),
        "cameraAngle": _coerce_enum(_norm_str(raw.get("cameraAngle")), _CAMERA_ANGLES, "平视"),
        "dof": _norm_str(raw.get("dof")),
        "lighting": _norm_str(raw.get("lighting")),
        "colorMood": _norm_str(raw.get("colorMood")),
        "negativeShort": _norm_str(raw.get("negativeShort")),
        "useDirectPrompt": use_dp and bool(direct),
        "directPrompt": direct if use_dp else "",
    }


def _heuristic_visual_panel(panel: dict[str, Any]) -> dict[str, Any]:
    paint = panel.get("paint") if isinstance(panel.get("paint"), dict) else {}
    script = panel.get("script") if isinstance(panel.get("script"), dict) else {}
    pb = paint.get("promptBlocks") if isinstance(paint.get("promptBlocks"), dict) else {}

    subj = _norm_str(pb.get("subject"))
    sett = _norm_str(pb.get("setting"))
    lit = _norm_str(pb.get("lighting"))
    cam = _norm_str(pb.get("camera"))
    moment = _norm_str(pb.get("moment"))
    qual = _norm_str(pb.get("qualityHint"))
    composed = _compose_positive_from_prompt_blocks(paint)
    pos = composed if composed else _norm_str(paint.get("positivePrompt"))
    neg = _norm_str(paint.get("negativePrompt"))
    cont = _norm_str(paint.get("continuity"))
    tags = paint.get("styleTags")
    tag_line = ""
    if isinstance(tags, list) and tags:
        tag_line = "，".join(_norm_str(x) for x in tags[:8] if _norm_str(x))
    cref = paint.get("characterRefIds")
    cref_line = ""
    if isinstance(cref, list) and cref:
        cref_line = "角色引用：" + "，".join(_norm_str(x) for x in cref[:6] if _norm_str(x))
    nar = _norm_str(script.get("narration"))

    # 空镜 / 无人物：不往角色栏塞旁白或环境句
    blob = f"{subj}\n{moment}\n{pos}\n{nar}"
    empty_shot_zh = (
        "空镜",
        "无人",
        "无人物",
        "无人出现",
        "不含人物",
        "无主体人物",
        "纯环境",
        "纯景物",
    )
    empty_shot_en = (
        "establishing",
        "no people",
        "without people",
        "empty street",
        "no characters",
    )
    blob_lower = blob.lower()
    looks_empty = any(m in blob for m in empty_shot_zh) or any(m in blob_lower for m in empty_shot_en)

    # 场景：setting 按顿号/逗号拆成 place / props 的粗拆
    scene_place = sett
    scene_tw = ""
    scene_props = ""
    if sett:
        chunks = [c.strip() for c in re.split(r"[，,、；;]", sett) if c.strip()]
        if len(chunks) >= 2:
            scene_place = chunks[0]
            scene_props = "，".join(chunks[1:])
        else:
            scene_place = sett

    if looks_empty or (not subj and not moment):
        fig1 = _empty_figure()
    else:
        fig1 = {"role": "", "costume": (subj[:200] if subj else ""), "action": (moment[:200] if moment else "")}
        # 仅当已有主体字段时，用旁白补 action，避免空镜仅靠旁白被误填成角色
        if nar and not fig1["action"] and (subj or moment):
            fig1["action"] = nar[:160]

    shot = _coerce_enum(cam, _SHOT_SCALES, "中景")
    ang = _coerce_enum(cam, _CAMERA_ANGLES, "平视")
    # camera 字段常混合景别与机位，再扫一遍 cam 字符串
    shot = _coerce_enum(cam + " " + subj, _SHOT_SCALES, shot)
    ang = _coerce_enum(cam + " " + moment, _CAMERA_ANGLES, ang)

    color_parts = [tag_line, qual]
    if cont:
        color_parts.insert(0, f"连贯：{cont}")
    if cref_line:
        color_parts.append(cref_line)
    color_mood = "；".join(p for p in color_parts if p)

    use_direct = False
    direct = ""
    if not (scene_place or fig1["costume"] or fig1["action"] or lit) and pos:
        use_direct = True
        direct = pos

    pid = _norm_str(panel.get("id")) or "sb-import"
    idx = _norm_str(panel.get("index")) or "01"

    raw_out = {
        "id": pid,
        "title": f"镜 {idx}",
        "scenePlace": scene_place,
        "sceneTimeWeather": scene_tw,
        "sceneProps": scene_props,
        "figures": [fig1, _empty_figure()],
        "shotScale": shot,
        "cameraAngle": ang,
        "dof": "",
        "lighting": lit,
        "colorMood": color_mood,
        "negativeShort": neg[:500] if neg else "",
        "useDirectPrompt": use_direct,
        "directPrompt": direct,
    }
    return _normalize_visual_panel(raw_out, fallback_id=pid, fallback_index=idx)


async def visual_panel_from_storyboard_paint(panel: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """返回 (visualPanel, source)。"""
    if not isinstance(panel, dict):
        panel = {}

    if not settings.deepseek_api_key:
        return _heuristic_visual_panel(panel), "heuristic"

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    user_payload = json.dumps({"panel": panel}, ensure_ascii=False, indent=2)
    if len(user_payload) > 24000:
        user_payload = user_payload[:24000] + "\n…（已截断）"

    try:
        resp = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": _SYS_LLM},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.25,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if not raw:
            raise RuntimeError("DeepSeek 返回空内容")
        data = _parse_json_object(raw)
        if not isinstance(data, dict):
            raise ValueError("顶层不是对象")
        idx = _norm_str(panel.get("index")) or "01"
        pid = _norm_str(panel.get("id")) or "sb-import"
        normalized = _normalize_visual_panel(data, fallback_id=pid, fallback_index=idx)
        return normalized, "llm"
    except Exception as e:
        logger.warning("visual_form LLM failed, fallback heuristic: %s", e)
        return _heuristic_visual_panel(panel), "heuristic"
