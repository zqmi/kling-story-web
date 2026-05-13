"""多节点大纲生成：LangGraph 顺序图 + DeepSeek（OpenAI 兼容）。

节点：项目信息 → 故事梗概 → 分幕 → 对白锚点；每步只产出该步 JSON，最后组装为
与前端 / DB 一致的 outline body（synopsis、acts、note、model，以及 project、anchors）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as e:  # pragma: no cover - 运行前需 pip install langgraph
    StateGraph = None  # type: ignore[misc, assignment]
    START = None  # type: ignore[misc, assignment]
    END = None  # type: ignore[misc, assignment]
    _LANGGRAPH_IMPORT_ERROR = e
else:
    _LANGGRAPH_IMPORT_ERROR = None


class OutlineGraphState(TypedDict, total=False):
    """LangGraph 状态：各节点向对应键写入结果。"""

    user_draft: str
    project_seed: dict[str, Any]
    project: dict[str, Any]
    synopsis: str
    note: str
    acts: list[dict[str, Any]]
    anchors: list[dict[str, Any]]


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型输出中未找到 JSON 对象")
    return json.loads(t[start : end + 1])


def _client() -> AsyncOpenAI:
    if not settings.deepseek_api_key:
        raise RuntimeError("未设置环境变量 DEEPSEEK_API_KEY")
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )


async def _complete_json(system: str, user: str, *, temperature: float = 0.55) -> dict[str, Any]:
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


_PLACEHOLDER_TOKENS = frozenset(
    {
        "待定",
        "待补充",
        "略",
        "无",
        "暂无",
        "tbd",
        "n/a",
        "na",
        "同上",
        "见上",
    }
)


def _is_placeholder_text(s: str, *, min_len: int = 1) -> bool:
    t = (s or "").strip()
    if len(t) < min_len:
        return True
    low = t.lower()
    if low in _PLACEHOLDER_TOKENS or t in _PLACEHOLDER_TOKENS:
        return True
    if t in ("—", "-", "…"):
        return True
    return False


def _project_constraints_ok(p: dict[str, Any]) -> bool:
    if _is_placeholder_text(str(p.get("title", "")), min_len=2):
        return False
    if _is_placeholder_text(str(p.get("subtitle", "")), min_len=4):
        return False
    if _is_placeholder_text(str(p.get("logline", "")), min_len=12):
        return False
    if _is_placeholder_text(str(p.get("format", "")), min_len=4):
        return False
    if _is_placeholder_text(str(p.get("scope", "")), min_len=4):
        return False
    if _is_placeholder_text(str(p.get("productionNote", "")), min_len=10):
        return False
    if _is_placeholder_text(str(p.get("synopsisNote", "")), min_len=80):
        return False
    tags = p.get("tags")
    if not isinstance(tags, list) or len(tags) < 3 or len(tags) > 6:
        return False
    for t in tags:
        if _is_placeholder_text(str(t), min_len=2):
            return False
    return True


def _synopsis_constraints_ok(synopsis: str) -> bool:
    s = (synopsis or "").strip()
    return len(s) >= 120 and not _is_placeholder_text(s, min_len=120)


def _clean_acts(raw: list[Any]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for a in raw:
        if not isinstance(a, dict):
            continue
        t = a.get("title") if isinstance(a.get("title"), str) else ""
        s = a.get("summary") if isinstance(a.get("summary"), str) else ""
        if t.strip() or s.strip():
            cleaned.append({"title": t.strip() or "未命名段落", "summary": s.strip()})
    return cleaned


def _acts_constraints_ok(acts: list[dict[str, Any]]) -> bool:
    if len(acts) < 5 or len(acts) > 7:
        return False
    for a in acts:
        if _is_placeholder_text(a.get("title", ""), min_len=4):
            return False
        if _is_placeholder_text(a.get("summary", ""), min_len=90):
            return False
    return True


_SYS_PROJECT = """你是中文编剧助理。你的任务是：根据**用户初稿**，一次性写满「项目与定位」页所需的**全部**字段（相当于制片表头 + 创作备忘），**全部由你生成**；用户侧草稿 JSON 仅作参考，不得以空字符串、单字、「待定」「待补充」「略」「无」「TBD」等敷衍。
只输出一个 JSON 对象（不要 markdown、不要解释），键名与类型严格如下（字符串用中文为主）：
{"title":"string","subtitle":"string","logline":"string","tags":["string", "..."],"format":"string","scope":"string","productionNote":"string","synopsisNote":"string"}
硬性要求（须全部满足）：
- title：具体作品名，不少于 2 个汉字。
- subtitle：点明体裁/气质，不少于 4 个汉字。
- logline：一句高概念梗概，不少于 12 个汉字。
- tags：恰好 3～6 条，每条 2～8 个汉字为宜。
- format：明确体裁与呈现形式（如 漫画短篇、动态漫、真人短片），不少于 4 个汉字。
- scope：明确目标篇幅（如 约 8～12P、3 分钟内,其中x和y是合适的数字,x和y都在12以内），不少于 4 个汉字。
- productionNote：制作向提示（渠道、节奏、禁忌、参考气质等），不少于 10 个汉字；若无禁忌请写「无特别禁忌；按常规短篇节奏推进」这类完整句。
- synopsisNote：**结构备忘**，不少于 80 个汉字；须包含：主线一句、副线或情绪线一句、至少 2 条伏笔/悬念点、必须交代的信息清单（分条写进同一段内亦可）。"""

_SYS_SYNOPSIS = """你是中文编剧助理。在已定「项目与定位」JSON（含 synopsisNote）与用户初稿下，写**完整故事梗概**与给作者的短备注。
只输出一个 JSON（不要 markdown、不要解释）：
{"synopsis":"string，一段故事梗概","note":"string，给作者的简短备注（结构/节奏/与备忘呼应等）；"}
要求：synopsis 须与项目、备忘、初稿一致；**梗概正文不少于 120 个汉字**（须写清主角动机、核心冲突、主要转折与落点方向）。"""

_SYS_ACTS = """你是中文编剧助理。你必须严格依据：**(1) 用户初稿 (2) 已定「项目与定位」JSON (3) 已定故事梗概**，划分 **5～7 幕**（大结构段），使全书式大纲**章节完整、可执行**。
只输出一个 JSON（不要 markdown、不要解释）：
{"acts":[{"title":"string，幕或段标题","summary":"string，本段叙事要点"}, ...]}
硬性要求：
- acts 条数：**至少 5 条、至多 7 条**。
- 每一条 summary：**不少于 90 个汉字**，须写清：本段情节推进、人物目标/阻力、冲突升级或信息增量、与前后幕的衔接；禁止只写一两句空泛概括。
- title 须点明本段在整体结构中的职责，每条不少于 4 个汉字。
- 幕序须覆盖从开端到收束的完整弧线，与初稿、项目定位、梗概不自相矛盾。"""

_SYS_ANCHORS = """你是中文编剧助理。根据已定项目、梗概与各幕要点，提炼少量固定对白/旁白锚点，供分镜与字幕引用。
只输出一个 JSON（不要 markdown、不要解释）：
{"anchors":[{"label":"string，短标签","text":"string，台词或旁白"}, ...]}
要求：4～8 条；每条 text 不宜过长。"""


def _merge_project(seed: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "title",
        "subtitle",
        "logline",
        "tags",
        "format",
        "scope",
        "productionNote",
        "synopsisNote",
    )
    out: dict[str, Any] = {}
    for k in keys:
        v = llm.get(k)
        if k == "tags":
            if isinstance(v, list) and v:
                out[k] = [str(x) for x in v if str(x).strip()][:8]
            elif isinstance(seed.get(k), list):
                out[k] = list(seed[k])
            else:
                out[k] = []
        else:
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()
            elif isinstance(seed.get(k), str):
                out[k] = seed[k]
            else:
                out[k] = ""
    return out


async def node_project(state: OutlineGraphState) -> dict[str, Any]:
    seed = state.get("project_seed") or {}
    draft = (state.get("user_draft") or "").strip()
    user = (
        "任务：写满「项目与定位」全部字段。下列「项目草稿」仅作线索，**最终以你根据初稿推断的成稿为准**。\n"
        "当前项目草稿（JSON）：\n"
        + json.dumps(seed, ensure_ascii=False)
        + "\n\n用户初稿：\n"
        + draft
    )
    data = await _complete_json(_SYS_PROJECT, user, temperature=0.45)
    project = _merge_project(seed, data)
    if not _project_constraints_ok(project):
        raise ValueError("项目与定位未能按规则写满，请重试或调整初稿")
    return {"project": project}


async def node_synopsis(state: OutlineGraphState) -> dict[str, Any]:
    project = state.get("project") or {}
    draft = (state.get("user_draft") or "").strip()
    user = (
        "以下为已定「项目与定位」（须严格一致，勿矛盾）：\n"
        + json.dumps(project, ensure_ascii=False)
        + "\n\n用户初稿：\n"
        + draft
    )
    data = await _complete_json(_SYS_SYNOPSIS, user, temperature=0.55)
    synopsis = data.get("synopsis") if isinstance(data.get("synopsis"), str) else ""
    note = data.get("note") if isinstance(data.get("note"), str) else ""
    synopsis = synopsis.strip()
    note = note.strip()
    if not _synopsis_constraints_ok(synopsis):
        raise ValueError("故事梗概未能写满至要求长度，请重试")
    return {"synopsis": synopsis, "note": note}


async def node_acts(state: OutlineGraphState) -> dict[str, Any]:
    project = state.get("project") or {}
    synopsis = (state.get("synopsis") or "").strip()
    draft = (state.get("user_draft") or "").strip()
    user = (
        "以下为已定信息，分幕须**严格依据**三者且写满每幕；不得引入与项目/梗概无关的新主线。\n"
        "（1）项目与定位（JSON）：\n"
        + json.dumps(project, ensure_ascii=False)
        + "\n\n（2）故事梗概：\n"
        + synopsis
        + "\n\n（3）用户初稿：\n"
        + draft
    )
    data = await _complete_json(_SYS_ACTS, user, temperature=0.55)
    raw = data.get("acts")
    acts_raw: list[Any] = raw if isinstance(raw, list) else []
    cleaned = _clean_acts(acts_raw)
    if not _acts_constraints_ok(cleaned):
        raise ValueError("分幕未能按规则写满（须 5～7 幕、每幕 summary 不少于 90 字），请重试")
    return {"acts": cleaned}


async def node_anchors(state: OutlineGraphState) -> dict[str, Any]:
    project = state.get("project") or {}
    synopsis = (state.get("synopsis") or "").strip()
    acts = state.get("acts") or []
    draft = (state.get("user_draft") or "").strip()
    user = (
        "项目信息（JSON）：\n"
        + json.dumps(project, ensure_ascii=False)
        + "\n\n故事梗概：\n"
        + synopsis
        + "\n\n分幕要点（JSON）：\n"
        + json.dumps(acts, ensure_ascii=False)
        + "\n\n用户初稿：\n"
        + draft
    )
    data = await _complete_json(_SYS_ANCHORS, user, temperature=0.5)
    raw = data.get("anchors")
    rows: list[dict[str, Any]] = raw if isinstance(raw, list) else []
    cleaned: list[dict[str, Any]] = []
    for a in rows:
        if not isinstance(a, dict):
            continue
        lab = a.get("label") if isinstance(a.get("label"), str) else ""
        text = a.get("text") if isinstance(a.get("text"), str) else ""
        if lab.strip() or text.strip():
            cleaned.append({"label": lab.strip() or "锚点", "text": text.strip()})
    if len(cleaned) < 1:
        cleaned = [{"label": "旁白", "text": "（请在此补充关键旁白或对白）"}]
    return {"anchors": cleaned}


def _build_graph():
    if StateGraph is None or START is None or END is None:
        raise RuntimeError(
            "未安装 langgraph，请在 backend 目录执行：pip install -r requirements.txt"
        ) from _LANGGRAPH_IMPORT_ERROR

    g = StateGraph(OutlineGraphState)
    g.add_node("project", node_project)
    g.add_node("synopsis", node_synopsis)
    g.add_node("acts", node_acts)
    g.add_node("anchors", node_anchors)
    g.add_edge(START, "project")
    g.add_edge("project", "synopsis")
    g.add_edge("synopsis", "acts")
    g.add_edge("acts", "anchors")
    g.add_edge("anchors", END)
    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def _assemble_body(final: OutlineGraphState) -> dict[str, Any]:
    return {
        "synopsis": (final.get("synopsis") or "").strip(),
        "acts": list(final.get("acts") or []),
        "note": (final.get("note") or "").strip(),
        "model": settings.deepseek_model,
        "project": dict(final.get("project") or {}),
        "anchors": list(final.get("anchors") or []),
    }


async def generate_outline_langgraph(payload: dict[str, Any]) -> dict[str, Any]:
    """入口：与旧版 `_deepseek_generate_outline` 相同的 payload 形状。"""
    user_draft = (payload.get("userDraft") or "").strip()
    if not user_draft:
        raise ValueError("userDraft 不能为空")
    project_seed = dict(payload.get("project") or {})
    initial: OutlineGraphState = {
        "user_draft": user_draft,
        "project_seed": project_seed,
    }
    graph = _get_graph()
    final = await graph.ainvoke(initial)
    body = _assemble_body(final)
    logger.info(
        "langgraph outline done acts=%s anchors=%s",
        len(body.get("acts") or []),
        len(body.get("anchors") or []),
    )
    return body
