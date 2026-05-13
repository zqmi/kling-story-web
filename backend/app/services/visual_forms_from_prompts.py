"""全表主/负提示 → 描写页多镜表单（严格 JSON，顺序与输入 shots 一致）。

LLM 按 **3～5 镜一批** 调用，减轻单次输出过长导致的细节不足；各批结果按原序拼接。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.storyboard_llm import _norm_str
from app.services.visual_form_from_paint import _heuristic_visual_panel, _normalize_visual_panel

logger = logging.getLogger(__name__)

_MAX_SHOTS = 40
_MAX_PROMPT_LEN = 2000
_CHUNK_LO = 3
_CHUNK_HI = 5
_MAX_CONCURRENT_CHUNKS = 2

_SYS_BATCH = """你是影视与 AI 绘画提示词拆解编辑。用户会提供一个 JSON，键为 **shots**（数组）。

**本批请求**：`shots` 为 **一小段连续镜**（通常 **3～5 条**；项目很短时可能 1～2 条）。你只需为本批生成等长的 `panels`，写细、写具体，不必挂念其它镜。

每个 shot **只**含这些键（勿要求其它键）：
- `id`（字符串）、`index`（字符串，如 "01"）
- `positivePrompt`：主提示（文生图正面描述）
- `negativePrompt`：负向排除
- `narration`：可选字符串，本镜旁白一句；拆字段时须与主提示一致，勿矛盾

你的任务：对 **本批每一个** shot 生成一条「描写页」用的结构化记录，信息**全部**从该 shot 的 positivePrompt、negativePrompt、narration 提炼，**禁止**编造与输入无关的剧情。

只输出**一个** JSON 对象（不要 markdown、不要代码围栏、不要编号列表说明），且顶层**仅有**键 `panels`：
{"panels":[ ... ]}

硬性规则：
1. `panels` 数组长度**必须等于**本批 `shots` 长度。
2. **顺序一致**：`panels[i]` 对应 `shots[i]`（同一镜）。
3. 每个 `panels[i]` **且仅包含**下列键（勿增删键名；字符串勿用 null，用 ""）：
   - `id`：必须等于 `shots[i].id`
   - `index`：必须等于 `shots[i].index`
   - `title`：如 `镜 01`，与 index 对齐
   - `scenePlace`：地点/空间，尽量具体可画
   - `sceneTimeWeather`：时间与天气
   - `sceneProps`：关键陈设/道具
   - `figures`：恰好 **2** 个对象；每个仅有 `role`、`costume`、`action` 三键。**空镜 / 纯环境 / 无人物** 时两个对象可**全部为 `""`**，勿为凑字段虚构人物。仅当主提示或旁白明确存在可画主体（人、动物、拟人化角色等）时，再写入角色 1；有第二主体再写角色 2，否则角色 2 全 `""`。
   - **`costume`（服饰要点，有人物时重点）**：动笔前先在脑中**扫读**本镜 `positivePrompt` 与 `narration`，列出所有与**穿戴/发型段落/帽鞋袜包/首饰眼镜徽章/制服形制与色差/污渍淋湿/布料厚薄褶皱与反光**有关的词，**尽量写进 `costume`**，不要把主提示里已经写明的领带、护腕、第二件叠穿、裤管鞋面等信息留在句外却只写一句「校服」。**禁止**在仍有可拆线索时，用「某类服装 + 单点状态」**标签式**敷衍完事（典型反例：仅「校服，袖口被雨水打湿」一行结束，而主提示另有领口、配饰、裤脚、书包压痕等未写入）。**至少**组织 **2～3 个互不重复的可视信息**（例：上装色感与形制 + 淋湿或褶皱范围与边界 + 书包肩带或桌面接触造成的压褶/形变 + 小配饰）；若原文确只有「校服」级词，在不编造新款新色的前提下，用**裁剪裁影、褶皱走向、与雨水或体温相关的布料状态**补成一小段，仍须与主提示一致。**大环境光、冷暖对比、脸庞被柔光笼罩**等以 `lighting`、`colorMood` 为主；`costume` 最多用半句点到「领口/袖口布料与肤色的受光交界」，避免与光色字段整段重复。**`action`** 专写走位、手势、表情、递物等戏剧动作，勿把叙事长句堆进 `costume`。
   - `shotScale`：必须是之一：特写、中近景、中景、中全景、全景、大远景
   - `cameraAngle`：必须是之一：平视、略俯、略仰、顶视、低机位
   - `dof`：景深/构图，尽量写出画面重心（如焦点落在何处）
   - `lighting`：主光/照明，尽量具体（方向、软硬、冷暖对比）
   - `colorMood`：色调与氛围
   - `negativeShort`：从 `negativePrompt` 压缩成短排除说明（勿把正面剧情再写一遍）

不要输出 `useDirectPrompt`、`directPrompt`、`promptBlocks` 等其它键。"""

_SYS_CHARACTER_ANCHOR = """你是影视造型与角色外观统筹。用户 JSON 含 **shots** 数组（全部分镜镜位），每项含 `id`、`index`、`positivePrompt`、`negativePrompt`、`narration`。

任务：通读**所有**镜头的主提示与旁白，提炼跨镜**重复出现或可推断为同一人物**的**稳定外观锚定**：衣着形制与主色、发型发色、体态年龄段、标志性配饰（若有）；写成一段 **80～380 字**的中文说明。该段将置于每镜文生图主提示最前作为「全镜共用外观」，因此：
- 只写**相对稳定**的装束与外形，**不要**写逐镜剧情动作、走位、具体台词。
- 若各镜人物杂乱、无重复主体，则写**最主要**可见角色的外观；确实无可归纳信息时输出空字符串。

只输出**一个** JSON 对象，顶层**仅有**键 `characterStyleAnchor`（字符串；无信息时为 ""）：
{"characterStyleAnchor":"……"}
"""


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型输出中未找到 JSON 对象")
    return json.loads(t[start : end + 1])


def _clip_prompt(s: str, n: int) -> str:
    t = (s or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _chunk_ranges(n: int) -> list[tuple[int, int]]:
    """将 [0, n) 切成若干半开区间 [start, end)，每段长度在 [_CHUNK_LO, _CHUNK_HI] 内（总长 <3 时整段一次）。"""
    if n <= 0:
        return []
    if n <= _CHUNK_HI:
        return [(0, n)]
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < n:
        rem = n - start
        if rem <= _CHUNK_HI:
            ranges.append((start, n))
            break
        # rem > 5：避免尾段只剩 1～2 条无法成批
        if rem == 6:
            c = 3
        elif rem == 7:
            c = 3
        else:
            c = 4
        ranges.append((start, start + c))
        start += c
    return ranges


def _shot_item_to_fake_panel(it: dict[str, Any]) -> dict[str, Any]:
    """供规则兜底复用 heuristic。"""
    return {
        "id": _norm_str(it.get("id")) or "sb",
        "index": _norm_str(it.get("index")) or "01",
        "script": {"narration": _norm_str(it.get("narration"))},
        "paint": {
            "positivePrompt": _norm_str(it.get("positivePrompt")),
            "negativePrompt": _norm_str(it.get("negativePrompt")),
            "promptBlocks": {},
        },
    }


def _heuristic_row(it: dict[str, Any]) -> dict[str, Any]:
    fake = _shot_item_to_fake_panel(it)
    row = _heuristic_visual_panel(fake)
    idx = _norm_str(it.get("index")) or "01"
    pid = _norm_str(it.get("id")) or row["id"]
    return _normalize_visual_panel(
        {**row, "id": pid, "title": f"镜 {idx}", "useDirectPrompt": False, "directPrompt": ""},
        fallback_id=pid,
        fallback_index=idx,
    )


def _heuristic_character_style_anchor(panels: list[dict[str, Any]]) -> str:
    """无 LLM 或 LLM 失败时从已生成的 figures 服饰/称呼拼一条短锚定。"""
    bits: list[str] = []
    seen: set[str] = set()
    for p in panels:
        figs = p.get("figures")
        if not isinstance(figs, list):
            continue
        for f in figs[:2]:
            if not isinstance(f, dict):
                continue
            r = _norm_str(f.get("role"))
            c = _norm_str(f.get("costume"))
            if not c and not r:
                continue
            key = f"{r}|{c}"
            if key in seen:
                continue
            seen.add(key)
            if r and c:
                bits.append(f"{r}：{c}")
            elif c:
                bits.append(c)
    out = "；".join(bits)
    if not out:
        return ""
    return _clip_prompt(out, 520)


async def _llm_character_style_anchor(client: AsyncOpenAI, shots: list[dict[str, Any]]) -> str:
    """全表 shots 一次调用，生成 characterStyleAnchor。"""
    payload = json.dumps({"shots": shots}, ensure_ascii=False, indent=2)
    if len(payload) > 24000:
        payload = payload[:24000] + "\n…（shots 已截断）"
    resp = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": _SYS_CHARACTER_ANCHOR},
            {"role": "user", "content": payload},
        ],
        temperature=0.25,
    )
    raw_txt = (resp.choices[0].message.content or "").strip()
    if not raw_txt:
        return ""
    data = _parse_json_object(raw_txt)
    v = data.get("characterStyleAnchor")
    if isinstance(v, str):
        return v.strip()[:2000]
    return ""


def _normalize_llm_panel(
    raw: dict[str, Any],
    *,
    expect_id: str,
    expect_index: str,
) -> dict[str, Any]:
    merged = {**raw, "id": _norm_str(raw.get("id")) or expect_id, "index": _norm_str(raw.get("index")) or expect_index}
    merged["useDirectPrompt"] = False
    merged["directPrompt"] = ""
    return _normalize_visual_panel(merged, fallback_id=expect_id, fallback_index=expect_index)


async def _llm_expand_chunk(
    client: AsyncOpenAI,
    chunk: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对本批 3～5 条 shot 调一次 LLM，返回与 chunk 等长的规范化 panels。"""
    payload = json.dumps({"shots": chunk}, ensure_ascii=False, indent=2)
    if len(payload) > 28000:
        payload = payload[:28000] + "\n…（shots 已截断）"

    resp = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": _SYS_BATCH},
            {"role": "user", "content": payload},
        ],
        temperature=0.2,
    )
    raw_txt = (resp.choices[0].message.content or "").strip()
    if not raw_txt:
        raise RuntimeError("DeepSeek 返回空内容")
    data = _parse_json_object(raw_txt)
    panels_raw = data.get("panels")
    if not isinstance(panels_raw, list):
        raise ValueError("缺少 panels 数组")

    out: list[dict[str, Any]] = []
    for i, it in enumerate(chunk):
        expect_id = it["id"]
        expect_index = it["index"]
        pr = panels_raw[i] if i < len(panels_raw) and isinstance(panels_raw[i], dict) else {}
        out.append(_normalize_llm_panel(pr, expect_id=expect_id, expect_index=expect_index))

    if len(out) != len(chunk):
        raise ValueError("panels 长度与本批 shots 不一致")
    return out


async def visual_forms_from_prompts_batch(
    shots: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, str]:
    """输入精简 shots，返回 (panels, source, characterStyleAnchor)。

    `characterStyleAnchor`：有 DeepSeek 时在整表 panels 生成后再 **单独一次 LLM** 归纳；否则由规则从 panels 摘要。
    """
    clean: list[dict[str, Any]] = []
    for s in shots[:_MAX_SHOTS]:
        if not isinstance(s, dict):
            continue
        clean.append(
            {
                "id": _norm_str(s.get("id")) or f"sb-{len(clean):03d}",
                "index": _norm_str(s.get("index")) or f"{len(clean) + 1:02d}",
                "positivePrompt": _clip_prompt(_norm_str(s.get("positivePrompt")), _MAX_PROMPT_LEN),
                "negativePrompt": _clip_prompt(_norm_str(s.get("negativePrompt")), _MAX_PROMPT_LEN),
                "narration": _clip_prompt(_norm_str(s.get("narration")), 600),
            }
        )
    if not clean:
        return [], "heuristic", ""

    if not settings.deepseek_api_key:
        rows = [_heuristic_row(it) for it in clean]
        return rows, "heuristic", _heuristic_character_style_anchor(rows)

    ranges = _chunk_ranges(len(clean))
    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    sem = asyncio.Semaphore(_MAX_CONCURRENT_CHUNKS)

    async def _run_slice(slice_index: int, start: int, end: int) -> tuple[int, list[dict[str, Any]], bool]:
        chunk = clean[start:end]
        async with sem:
            try:
                panels = await _llm_expand_chunk(client, chunk)
                return slice_index, panels, True
            except Exception as e:
                logger.warning(
                    "visual_forms_from_prompts chunk LLM failed [%s:%s], heuristic fallback: %s",
                    start,
                    end,
                    e,
                )
                return slice_index, [_heuristic_row(it) for it in chunk], False

    tasks = [_run_slice(i, s, e) for i, (s, e) in enumerate(ranges)]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[0])
    merged: list[dict[str, Any]] = []
    any_llm = False
    all_llm = True
    for _, panels, ok in results:
        merged.extend(panels)
        if ok:
            any_llm = True
        else:
            all_llm = False

    if len(merged) != len(clean):
        logger.error(
            "visual_forms_from_prompts merged length mismatch: %s != %s",
            len(merged),
            len(clean),
        )
        rows = [_heuristic_row(it) for it in clean]
        return rows, "heuristic", _heuristic_character_style_anchor(rows)

    if all_llm:
        source = "llm"
    elif any_llm:
        source = "llm+heuristic"
    else:
        source = "heuristic"

    anchor = ""
    if settings.deepseek_api_key:
        try:
            anchor = await _llm_character_style_anchor(client, clean)
        except Exception as e:
            logger.warning("character_style_anchor LLM failed: %s", e)
            anchor = _heuristic_character_style_anchor(merged)

    return merged, source, (anchor or "").strip()
