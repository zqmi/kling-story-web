"""分镜三节点线性管线：normalize（程序）→ plan（LLM 镜位规划）→ expand（LLM 填 paint + script）。

一次 expand 产出全部 panels；每镜以连续叙述 **script.narration** 为主（**dialogue** 固定留空）。"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, TypedDict

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.storyboard_llm import normalize_llm_panels

logger = logging.getLogger(__name__)

_ASPECT = frozenset({"1:1", "3:4", "4:3", "16:9", "21:9", "9:16"})


class StoryboardPipelineState(TypedDict, total=False):
    job_id: str
    outline_in: dict[str, Any]
    outline_norm: dict[str, Any]
    shot_plan: list[dict[str, Any]]
    panels_raw: list[dict[str, Any]]


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型输出中未找到 JSON 对象")
    return json.loads(t[start : end + 1])


def _client() -> AsyncOpenAI:
    if not settings.deepseek_api_key:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY")
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )


async def _complete_json(system: str, user: str, *, temperature: float = 0.35) -> dict[str, Any]:
    client = _client()
    resp = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        raise RuntimeError("DeepSeek 返回空内容")
    return _parse_json_object(raw)


_SYS_PLAN = """你是分镜统筹。根据用户给出的大纲 JSON（含 project、synopsis、acts[].beats、anchors），只做**分镜规划**，不写绘画长提示。

只输出一个 JSON 对象（不要 markdown、不要解释）：
{"shots":[{"actIndex": number,"beatId": string,"dialogueRef": string,"narrativeFocus": string,"suggestedAspectRatio": string}, ...]}

字段说明：
- actIndex：从 0 起的幕序号，与 acts 数组下标一致。
- beatId：必须与对应 beat 的 id 字符串一致（若大纲里某 beat 无 id，用你在大纲里能看到的 id；大纲若已补全 id 则照抄）。
- dialogueRef：若本镜建议对齐某对白锚点，填 anchors 中可稳定引用的短 slug（如 anchor-a）；否则空字符串 ""。
- narrativeFocus：一句话说明本镜叙事/视觉任务（给下一步「扩写绘画提示」用），40～120 汉字为宜。
- suggestedAspectRatio：只能是之一：1:1、3:4、4:3、16:9、21:9、9:16。

规则：
- 通常每个 beat 至少 1 条 shot；相邻极短节拍可合并为 1 条，并在 narrativeFocus 写清涵盖内容。
- 总条数不超过 35。
"""


_SYS_EXPAND = """你是 AI 绘画与分镜台本助手。用户 JSON 含：（1）outline 大纲；（2）shot_plan 规划数组。

请为 shot_plan 中**每一条**生成**恰好一个** panel，数组顺序与 shot_plan **完全一致**（第 i 个 panel 对应第 i 个 shot）。

只输出：{"panels":[ ... ]}，不要 markdown、不要其它文字。

## script（连续叙述旁白，与画面强绑定）
每个 panel 必须包含 **script** 对象，键不可省略：
- **narration**（必填，非空字符串）：本镜**一句**第三人称叙述旁白（20～120 字为宜），写清本镜画面推进了什么、观众应感知到的信息与情绪；须与 paint.promptBlocks 的 subject、setting、moment **同屏一致**，禁止与画面矛盾。
- **连续性**：panels 数组按镜序阅读时，各镜 **narration** 须像**同一段连续口播稿**自然衔接——时间线不断裂、不重复上一句、可用指代与因果承接（「与此同时……」「他抬起头时……」），勿写成彼此无关的标题句堆砌。
- **dialogue**：固定写空字符串 ""（本产品不使用角色对白字段，勿填台词）。

## paint（强制 promptBlocks）
- id、index、trace（与 shot 一致）、paint 键不可省略。
- **promptBlocks**（对象，键名必须完全一致）：
  - subject / setting / lighting / camera / moment / qualityHint 要求同此前规范；positivePrompt 固定 ""。
- **negativePrompt**（必填，可短句）：只写「不要出现什么」——畸形肢体、水印、过度锐化/HDR、乱入 UI 等；勿与主提示语义打架；勿把剧情正写再抄一遍。
- **continuity**（必填，首镜可 ""）：用 1～2 句说明与**前一镜 / 下一镜**在光源、空间、服装、天气、机位上的承接；首镜可写开场 establish 或留空字符串。
- **characterRefIds**（必填，数组）：每项一个稳定 slug（如 `char-a`）；无角色一致性需求时 `[]`。勿用空格拼接多个 id；**不要**输出多行字符串，应使用 JSON 数组。
- styleTags、aspectRatio（与 shot 的 suggestedAspectRatio 一致）同前。

禁止：narration 为空或与画面脱节；dialogue 非空；各镜旁白彼此跳跃无衔接；空洞套话、大段比喻；漏填 negativePrompt / continuity / characterRefIds 键。

示例（结构示意）：
{"panels":[{"id":"sb-x-001","index":"01","trace":{"actIndex":0,"beatId":"beat-0-0","dialogueRef":""},"script":{"dialogue":"","narration":"……"},"paint":{"promptBlocks":{"subject":"…","setting":"…","lighting":"…","camera":"…","moment":"…","qualityHint":"film still"},"positivePrompt":"","negativePrompt":"…","styleTags":["…"],"aspectRatio":"16:9","continuity":"","characterRefIds":[]}}]}"""


def normalize_outline_for_storyboard(outline: dict[str, Any]) -> dict[str, Any]:
    """程序规整：深拷贝、补 beats id、截断过长 synopsis。"""
    raw = copy.deepcopy(outline) if isinstance(outline, dict) else {}
    if not isinstance(raw.get("project"), dict):
        raw["project"] = {}
    if not isinstance(raw.get("acts"), list):
        raw["acts"] = []
    if not isinstance(raw.get("anchors"), list):
        raw["anchors"] = []
    syn = raw.get("synopsis")
    if isinstance(syn, str) and len(syn) > 12000:
        raw["synopsis"] = syn[:12000] + "…"

    for ai, act in enumerate(raw["acts"]):
        if not isinstance(act, dict):
            continue
        beats = act.get("beats")
        if not isinstance(beats, list):
            act["beats"] = []
            continue
        for bi, b in enumerate(beats):
            if not isinstance(b, dict):
                continue
            bid = str(b.get("id") or "").strip()
            if not bid:
                b["id"] = f"beat-{ai}-{bi}"
    return raw


def _default_shot_plan_from_outline(norm: dict[str, Any]) -> list[dict[str, Any]]:
    """规划 LLM 失败时，按节拍 1:1 生成占位 shot_plan。"""
    shots: list[dict[str, Any]] = []
    for ai, act in enumerate(norm.get("acts") or []):
        if not isinstance(act, dict):
            continue
        act_name = str(act.get("name") or act.get("title") or f"第{ai + 1}幕").strip()
        act_goal = str(act.get("dramaticGoal") or act.get("summary") or "").strip()
        beats = act.get("beats") if isinstance(act.get("beats"), list) else []
        if not beats:
            bid = ""
            shots.append(
                {
                    "actIndex": ai,
                    "beatId": bid,
                    "dialogueRef": "",
                    "narrativeFocus": (act_goal or act_name or "本幕过渡")[:200],
                    "suggestedAspectRatio": "16:9",
                }
            )
            continue
        for b in beats:
            if not isinstance(b, dict):
                continue
            bid = str(b.get("id") or "").strip()
            btype = str(b.get("type") or "其他").strip()
            content = str(b.get("content") or "").strip() or "（节拍）"
            shots.append(
                {
                    "actIndex": ai,
                    "beatId": bid,
                    "dialogueRef": "",
                    "narrativeFocus": f"{act_name} · {btype}：{content}"[:220],
                    "suggestedAspectRatio": "16:9",
                }
            )
    if not shots:
        synopsis = str(norm.get("synopsis") or "").strip()[:300]
        shots.append(
            {
                "actIndex": 0,
                "beatId": "",
                "dialogueRef": "",
                "narrativeFocus": synopsis or "（请在大纲中补充幕与节拍）",
                "suggestedAspectRatio": "16:9",
            }
        )
    return shots[:35]


def _normalize_shot_plan(shots: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in shots:
        if not isinstance(s, dict):
            continue
        try:
            ai = int(s.get("actIndex", 0))
        except (TypeError, ValueError):
            ai = 0
        ar = str(s.get("suggestedAspectRatio") or "16:9").strip()
        if ar not in _ASPECT:
            ar = "16:9"
        out.append(
            {
                "actIndex": ai,
                "beatId": str(s.get("beatId") or "").strip(),
                "dialogueRef": str(s.get("dialogueRef") or "").strip(),
                "narrativeFocus": str(s.get("narrativeFocus") or "").strip() or "（待扩写）",
                "suggestedAspectRatio": ar,
            }
        )
    return out[:35]


async def _node_plan(state: StoryboardPipelineState) -> dict[str, Any]:
    norm = state.get("outline_norm") or {}
    payload = json.dumps(norm, ensure_ascii=False, indent=2)
    if len(payload) > 28000:
        payload = payload[:28000] + "\n…（截断）"
    try:
        data = await _complete_json(_SYS_PLAN, payload, temperature=0.3)
    except Exception as e:
        logger.warning("storyboard plan LLM failed, fallback deterministic plan: %s", e)
        return {"shot_plan": _default_shot_plan_from_outline(norm)}

    raw_shots = data.get("shots")
    if not isinstance(raw_shots, list) or len(raw_shots) == 0:
        logger.warning("storyboard plan returned empty shots, using deterministic plan")
        return {"shot_plan": _default_shot_plan_from_outline(norm)}
    plan = _normalize_shot_plan(raw_shots)
    if not plan:
        return {"shot_plan": _default_shot_plan_from_outline(norm)}
    return {"shot_plan": plan}


async def _node_expand(state: StoryboardPipelineState) -> dict[str, Any]:
    norm = state.get("outline_norm") or {}
    plan = state.get("shot_plan") or []
    if not plan:
        raise RuntimeError("shot_plan 为空，无法 expand")
    user_obj = {"outline": norm, "shot_plan": plan}
    payload = json.dumps(user_obj, ensure_ascii=False, indent=2)
    if len(payload) > 30000:
        payload = payload[:30000] + "\n…（截断）"
    data = await _complete_json(_SYS_EXPAND, payload, temperature=0.35)
    panels = data.get("panels")
    if not isinstance(panels, list) or len(panels) == 0:
        raise RuntimeError("expand 阶段未返回非空 panels")
    if len(panels) != len(plan):
        logger.warning(
            "expand panels length %s != shot_plan %s, still normalizing",
            len(panels),
            len(plan),
        )
    return {"panels_raw": panels}


async def run_storyboard_linear_graph(outline: dict[str, Any], *, job_id: str) -> list[dict[str, Any]]:
    """normalize → plan → expand，返回规范化后的 panels。"""
    if not settings.deepseek_api_key:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY")

    st: StoryboardPipelineState = {
        "job_id": job_id,
        "outline_in": dict(outline) if isinstance(outline, dict) else {},
    }
    st["outline_norm"] = normalize_outline_for_storyboard(st["outline_in"])
    st.update(await _node_plan(st))
    st.update(await _node_expand(st))
    panels = normalize_llm_panels(st.get("panels_raw") or [], job_id=job_id)
    if not panels:
        raise RuntimeError("分镜管线结束后 panels 为空")
    return panels
