"""从大纲 JSON 调用 LLM 生成分镜 panels（与前端一致：`id`、`index`、可选 `trace`、`script`（narration 旁白 + 空 dialogue）、`paint`）。"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

_ASPECT_RATIOS = frozenset({"1:1", "3:4", "4:3", "16:9", "21:9", "9:16"})

# 与 expand 提示一致；有值则按序拼成 positivePrompt（优先于模型自填的长文）
_PROMPT_BLOCK_KEYS = ("subject", "setting", "lighting", "camera", "moment", "qualityHint")

_SYSTEM_PROMPT = """你是资深影视分镜师兼 AI 绘画提示词工程师。用户会提供「大纲 JSON」：
- project: 标题、logline、tags、制作口径等
- synopsis: 故事梗概
- acts: 每幕 name、dramaticGoal、beats[]（每项 id、type、content）
- anchors: 对白/旁白锚点（label、text），可与 dialogueRef 对齐

你的任务：为每一镜生成**可直接喂给文生图 API** 的结构化字段。**只输出一个合法 JSON 对象**，键名固定；不要 Markdown 代码围栏、不要输出 JSON 以外的任何文字、不要注释。

## 输出格式（严格）
{"panels":[ ... ]}

每个 panel 必须包含：
- id: 唯一字符串（建议 sb- 前缀 + 序号，勿重复）
- index: 两位字符串镜号 "01"、"02" … 与数组顺序一致
- **script**: 对象，键不可省略。
  - **narration**（必填）：本镜一句**连续叙述旁白**（第三人称），全片 panels 按序读起来须**前后衔接**；须与画面一致。
  - **dialogue**：固定 ""（不使用）。
- paint: 对象（字段缺一不可；无信息用空字符串 "" 或空数组 []，勿省略键）。**推荐**含 `promptBlocks`（六键齐全）；含则服务端以块拼接为主提示，`positivePrompt` 可置 ""。

### paint.promptBlocks（主提示的**强制拆解**，最重要；键名不可改）
用固定键写**短句**，只写可画事实，不写镜号。服务端会按顺序自动拼成 `positivePrompt`，你应把 **paint.positivePrompt 固定为 ""**（空字符串）。
- subject：画面中心主体（谁、体态与服装轮廓），约 10～60 字
- setting：地点与关键环境（陈设、天气介质），约 10～80 字
- lighting：主光方向、冷暖、曝光感，约 10～60 字
- camera：景别与机位，约 8～50 字
- moment：可见动作与表情（避免不可画的内心描写），约 10～90 字
- qualityHint：画质锚点，可少量英文；无则 ""

### paint.positivePrompt
与 promptBlocks 同时存在时以 **promptBlocks 拼接为准**；若仅走旧版可填一条连续自然语言（不推荐）。

禁止：空泛套话、大段比喻、与画面矛盾描述、整段只贴标签。

### paint.negativePrompt
只写「不要出现什么」：如畸形肢体、多余手指、文字水印、过度锐化/HDR、乱入的 UI/边框等；**不要**把正片内容再写一遍，**不要**与 positivePrompt 语义打架。

### paint.styleTags
3～10 个**短标签**（每词一般 2～8 字），写媒介/时代/气质关键词（如 电影静帧、雨夜、冷色调、窄巷）；**不要**把整段 positivePrompt 拆成标签列表。

### paint.aspectRatio
只能是之一：1:1、3:4、4:3、16:9、21:9、9:16。竖构图人物特写可 9:16；环境大景可 21:9 或 16:9；插画竖版可 3:4。与 `promptBlocks.camera` / 构图描述一致。

### paint.continuity
说明与**前一镜/下一镜**在光源、空间、服装、天气上的承接；首镜可写「开场Establish」类一句或留空字符串。

### paint.characterRefIds
本镜若需角色一致性，填**字符串数组**，每项一个稳定 slug（如 `char-protagonist-01`）；无则 `[]`。若 anchors / 大纲中有可引用身份，用同源 id，勿编造。服务端也接受**多行纯文本**（每行一个 ID），会规范为数组。

## 可选 trace（强烈建议填写）
- actIndex: 数字，对应幕序（从 0 起）
- beatId: 字符串，对应 beats[].id（有则必须一致）
- dialogueRef: 字符串，若本镜对齐某锚点/台词引用则填，否则可省略该键

## 镜头数量
与叙事节奏匹配：通常每个 beat 至少 1 镜，相邻极短节拍可合并；**单份 panels 建议不超过 35 镜**。"""


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型输出中未找到 JSON 对象")
    return json.loads(t[start : end + 1])


def _norm_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v.strip()
    return default


def _normalize_trace(tr: Any) -> dict[str, Any]:
    if not isinstance(tr, dict):
        return {}
    out: dict[str, Any] = {}
    if "actIndex" in tr and tr["actIndex"] is not None and tr["actIndex"] != "":
        try:
            out["actIndex"] = int(tr["actIndex"])
        except (TypeError, ValueError):
            pass
    bid = _norm_str(tr.get("beatId"))
    if bid:
        out["beatId"] = bid
    dr = _norm_str(tr.get("dialogueRef"))
    if dr:
        out["dialogueRef"] = dr
    return out


def _legacy_panel_to_paint(p: dict[str, Any]) -> dict[str, Any]:
    """旧版 scene/lens/characters → paint（供模型仍输出旧结构时兜底）。"""
    sc = p.get("scene") if isinstance(p.get("scene"), dict) else {}
    lens = p.get("lens") if isinstance(p.get("lens"), dict) else {}
    parts: list[str] = []
    merged = _norm_str(p.get("sceneMerged"))
    if merged:
        parts.append(merged)
    for k in ("background", "environment", "lightingColor"):
        t = _norm_str(sc.get(k))
        if t:
            parts.append(t)
    ss = _norm_str(lens.get("shotScale"))
    mv = _norm_str(lens.get("movement"))
    vp = _norm_str(lens.get("visualPoint"))
    if ss or mv:
        parts.append(f"景别与运镜：{ss} {mv}".strip())
    if vp:
        parts.append(f"画面要点：{vp}")
    chars = p.get("characters") if isinstance(p.get("characters"), list) else []
    for c in chars:
        if not isinstance(c, dict):
            continue
        nm = _norm_str(c.get("name"))
        bits = [nm, _norm_str(c.get("poseAction")), _norm_str(c.get("wardrobeHair"))]
        line = "，".join(x for x in bits if x)
        if line:
            parts.append(f"人物：{line}")
    positive = "；".join(parts) if parts else "（由旧字段合并，请在前端润色主提示）"
    return {
        "positivePrompt": positive,
        "negativePrompt": "低质量，畸形手指，多余肢体，文字水印，过度锐化",
        "styleTags": [],
        "aspectRatio": "16:9",
        "continuity": "",
        "characterRefIds": [],
    }


def _compose_positive_from_prompt_blocks(o: dict[str, Any]) -> str:
    pb = o.get("promptBlocks")
    if not isinstance(pb, dict):
        return ""
    parts: list[str] = []
    for k in _PROMPT_BLOCK_KEYS:
        t = _norm_str(pb.get(k))
        if t:
            parts.append(t)
    return "；".join(parts)


def _normalize_prompt_blocks(pb: Any) -> dict[str, str] | None:
    """保留六键结构供前端与绘画管线使用；非 dict 则省略。"""
    if not isinstance(pb, dict):
        return None
    return {k: _norm_str(pb.get(k)) for k in _PROMPT_BLOCK_KEYS}


def _parse_character_ref_ids(cr: Any) -> list[str]:
    """与前端「每行一个 ID」对齐：多行则按行；单行时可逗号/分号分隔。"""
    if isinstance(cr, list):
        return [_norm_str(x) for x in cr if _norm_str(x)]
    if isinstance(cr, str):
        text = cr.strip()
        if not text:
            return []
        lines = [ln.strip() for ln in re.split(r"\r?\n", text) if ln.strip()]
        if len(lines) > 1:
            return lines
        return [t.strip() for t in re.split(r"[,，;；]+", text) if t.strip()]
    return []


def _normalize_script(sc: Any) -> dict[str, Any]:
    o = sc if isinstance(sc, dict) else {}
    nar = _norm_str(o.get("narration"))
    if not nar:
        nar = "（待补旁白）"
    return {"dialogue": "", "narration": nar}


def _normalize_paint_dict(pt: Any) -> dict[str, Any]:
    o = pt if isinstance(pt, dict) else {}
    tags: list[str] = []
    st = o.get("styleTags")
    if isinstance(st, list):
        tags = [_norm_str(x) for x in st if _norm_str(x)]
    elif isinstance(st, str):
        tags = [t.strip() for t in re.split(r"[,，\n]", st) if t.strip()]
    ids = _parse_character_ref_ids(o.get("characterRefIds"))
    ar = _norm_str(o.get("aspectRatio"))
    if ar not in _ASPECT_RATIOS:
        ar = "16:9"
    composed = _compose_positive_from_prompt_blocks(o)
    raw_pos = _norm_str(o.get("positivePrompt"))
    positive = composed if composed else raw_pos
    neg = _norm_str(o.get("negativePrompt"))
    cont = _norm_str(o.get("continuity"))
    out: dict[str, Any] = {
        "positivePrompt": positive,
        "negativePrompt": neg,
        "styleTags": tags,
        "aspectRatio": ar,
        "continuity": cont,
        "characterRefIds": ids,
    }
    pb_norm = _normalize_prompt_blocks(o.get("promptBlocks"))
    if pb_norm is not None:
        out["promptBlocks"] = pb_norm
    return out


def normalize_llm_panels(raw: list[Any], *, job_id: str) -> list[dict[str, Any]]:
    """将模型返回的 panels 规范为前端结构（script：仅 narration 有效，dialogue 置空）、兼容旧 scene/lens 输出。"""
    out: list[dict[str, Any]] = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            continue
        pid = _norm_str(p.get("id")) or f"sb-llm-{job_id[:8]}-{i + 1:03d}"
        idx_str = _norm_str(p.get("index"))
        if not re.match(r"^\d{2}$", idx_str):
            idx_str = f"{i + 1:02d}"
        trace = _normalize_trace(p.get("trace"))

        paint_in = p.get("paint")
        cr_in = paint_in.get("characterRefIds") if isinstance(paint_in, dict) else None
        has_cr = bool(_parse_character_ref_ids(cr_in))
        has_pb_dict = isinstance(paint_in, dict) and isinstance(paint_in.get("promptBlocks"), dict)
        has_new_paint = isinstance(paint_in, dict) and (
            bool(_compose_positive_from_prompt_blocks(paint_in))
            or _norm_str(paint_in.get("positivePrompt"))
            or _norm_str(paint_in.get("negativePrompt"))
            or _norm_str(paint_in.get("continuity"))
            or has_cr
            or (isinstance(paint_in.get("styleTags"), list) and len(paint_in.get("styleTags") or []) > 0)
            or has_pb_dict
        )
        if has_new_paint:
            paint = _normalize_paint_dict(paint_in)
        elif p.get("scene") or p.get("lens") or p.get("sceneMerged") or p.get("characters"):
            paint = _normalize_paint_dict(_legacy_panel_to_paint(p))
        else:
            paint = _normalize_paint_dict(
                {"positivePrompt": _norm_str(p.get("positivePrompt")) or "（待补充主提示）"}
            )

        script = _normalize_script(p.get("script"))
        panel: dict[str, Any] = {"id": pid, "index": idx_str, "script": script, "paint": paint}
        if trace:
            panel["trace"] = trace
        out.append(panel)
    return out


async def generate_panels_from_outline_llm(outline: dict[str, Any], *, job_id: str) -> list[dict[str, Any]]:
    """调用 DeepSeek（OpenAI 兼容）从大纲生成 panels。"""
    if not settings.deepseek_api_key:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY，无法调用 LLM 生成分镜")

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    user_payload = json.dumps(outline, ensure_ascii=False, indent=2)
    if len(user_payload) > 28000:
        user_payload = user_payload[:28000] + "\n…（大纲已截断）"

    resp = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ],
        temperature=0.35,
    )
    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("DeepSeek 返回空内容")

    data = _parse_json_object(raw)
    panels_raw = data.get("panels")
    if not isinstance(panels_raw, list) or len(panels_raw) == 0:
        raise RuntimeError("模型 JSON 中缺少非空 panels 数组")

    panels = normalize_llm_panels(panels_raw, job_id=job_id)
    if not panels:
        raise RuntimeError("模型返回的 panels 无法规范化")
    return panels
