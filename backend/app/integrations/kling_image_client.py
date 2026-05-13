"""可灵（Kling）图像生成 HTTP 客户端（对齐 kling-story-pipeline-local story_agent）。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx

from app.integrations.kling_config import KlingConfig
from app.integrations.kling_jwt import build_kling_bearer_token

logger = logging.getLogger(__name__)


class KlingImageError(Exception):
    """可灵图像接口业务或 HTTP 错误。"""


def _urls_from_task_result(tr: dict[str, Any]) -> list[str]:
    out: list[str] = []
    imgs = tr.get("images")
    if not isinstance(imgs, list):
        return out
    for item in imgs:
        if isinstance(item, str) and item.startswith(("http://", "https://")):
            out.append(item)
        elif isinstance(item, dict):
            u = item.get("url") or item.get("image_url")
            if isinstance(u, str) and u.startswith(("http://", "https://")):
                out.append(u)
    return out


def _extract_urls(payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str | None) -> None:
        if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            out.append(u)

    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                add(item.get("url") or item.get("image_url"))
    elif isinstance(data, dict):
        add(data.get("url") or data.get("image_url"))
        inner = data.get("task_result")
        if isinstance(inner, dict):
            for u in _urls_from_task_result(inner):
                add(u)

    tr = payload.get("task_result")
    if isinstance(tr, dict):
        for u in _urls_from_task_result(tr):
            add(u)

    return out


def _extract_task_id(payload: dict[str, Any]) -> str | None:
    for key in ("task_id", "request_id", "id"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            return v
    data = payload.get("data")
    if isinstance(data, dict):
        v = data.get("task_id")
        if isinstance(v, str) and v:
            return v
    return None


def raise_if_api_code_error(payload: dict[str, Any]) -> None:
    code = payload.get("code")
    if code is None:
        return
    if code == 0:
        return
    msg = (
        payload.get("message")
        or payload.get("msg")
        or payload.get("status_message")
        or payload.get("task_status_msg")
        or str(payload)[:2000]
    )
    raise KlingImageError(f"可灵业务错误 code={code}: {msg}")


def _task_status(payload: dict[str, Any]) -> str | None:
    s = payload.get("task_status") or payload.get("status")
    if s is None:
        data = payload.get("data")
        if isinstance(data, dict):
            s = data.get("task_status") or data.get("status")
    if isinstance(s, str):
        return s.lower()
    return None


def _is_terminal_success(status: str | None, urls: list[str]) -> bool:
    if not urls:
        return False
    if status is None:
        return True
    return status in ("succeed", "success", "completed", "done")


def _is_terminal_failure(status: str | None) -> bool:
    if status is None:
        return False
    return status in ("failed", "error", "cancelled", "canceled")


@dataclass
class KlingImageResult:
    urls: list[str]
    task_id: str | None
    model_name: str


class KlingImageClient:
    """文生图：POST …/v1/images/generations，必要时 GET …/v1/images/generations/{task_id}。"""

    def __init__(self, cfg: KlingConfig) -> None:
        self._base = cfg.kling_api_base.rstrip("/")
        self._access = (cfg.kling_access_key or "").strip()
        self._secret = (cfg.kling_secret_key or "").strip()
        self._api_key = (cfg.kling_api_key or "").strip()
        self._jwt_ttl = cfg.kling_jwt_ttl_seconds
        self._model = cfg.kling_image_model_name.strip() or "kling-v1"
        mf = (cfg.kling_image_model_field or "model").strip().lower()
        self._model_field = "model_name" if mf == "model_name" else "model"
        self._create_path = cfg.kling_image_generations_path
        self._task_prefix = cfg.kling_image_tasks_path_prefix.rstrip("/")
        self._timeout = cfg.kling_http_timeout_seconds
        self._poll_interval = cfg.kling_poll_interval_seconds
        self._poll_max = cfg.kling_poll_max_seconds

    def configured(self) -> bool:
        if self._api_key:
            return True
        return bool(self._access and self._secret)

    def _bearer_token(self) -> str:
        if self._api_key:
            t = self._api_key
            if t.lower().startswith("bearer "):
                return t[7:].strip()
            return t
        if self._access and self._secret:
            return build_kling_bearer_token(
                self._access,
                self._secret,
                ttl_seconds=self._jwt_ttl,
            )
        raise KlingImageError("未配置可灵鉴权：请设置 KLING_ACCESS_KEY+KLING_SECRET_KEY，或 KLING_API_KEY")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._bearer_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _build_generation_body(
        self,
        prompt: str,
        *,
        n: int = 1,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
        negative_prompt: str | None = None,
        image: str | None = None,
        image_reference: str | None = None,
        image_fidelity: float | None = None,
        human_fidelity: float | None = None,
        callback_url: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            self._model_field: self._model,
            "prompt": prompt,
            "n": n,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        if image:
            body["image"] = image
        if image_reference:
            body["image_reference"] = image_reference
        if image_fidelity is not None:
            body["image_fidelity"] = image_fidelity
        if human_fidelity is not None:
            body["human_fidelity"] = human_fidelity
        if callback_url:
            body["callback_url"] = callback_url
        return body

    async def _post_generation(self, body: dict[str, Any]) -> dict[str, Any]:
        create_url = f"{self._base}{self._create_path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                create_url,
                headers=self._headers(),
                json=body,
            )
            if resp.status_code >= 400:
                detail = resp.text[:2000]
                if resp.status_code == 401:
                    detail += (
                        " 鉴权提示：KLING_API_BASE 须为 https://api-beijing.klingai.com；"
                        "核对 AK/SK；存在 KLING_API_KEY 时会覆盖 AK+SK JWT。"
                    )
                raise KlingImageError(
                    f"可灵生图 HTTP {resp.status_code}: {detail}",
                )
            return resp.json()

    async def generate(
        self,
        prompt: str,
        *,
        n: int = 1,
        aspect_ratio: str = "1:1",
        resolution: str = "1k",
        negative_prompt: str | None = None,
        image: str | None = None,
        image_reference: str | None = None,
        image_fidelity: float | None = None,
        human_fidelity: float | None = None,
        callback_url: str | None = None,
    ) -> KlingImageResult:
        if not self.configured():
            raise KlingImageError("未配置可灵鉴权：请设置 KLING_ACCESS_KEY+KLING_SECRET_KEY，或 KLING_API_KEY")

        body = self._build_generation_body(
            prompt,
            n=n,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            negative_prompt=negative_prompt,
            image=image,
            image_reference=image_reference,
            image_fidelity=image_fidelity,
            human_fidelity=human_fidelity,
            callback_url=callback_url,
        )
        payload = await self._post_generation(body)

        raise_if_api_code_error(payload)

        urls = _extract_urls(payload)
        status = _task_status(payload)
        tid = _extract_task_id(payload)

        if _is_terminal_failure(status):
            msg = (
                payload.get("status_message")
                or payload.get("message")
                or payload.get("task_status_msg")
                or str(payload)
            )
            raise KlingImageError(f"可灵任务失败: {msg}")

        if _is_terminal_success(status, urls):
            return KlingImageResult(urls=urls, task_id=tid, model_name=self._model)

        if tid and not urls:
            payload = await self._poll_task(tid)
            raise_if_api_code_error(payload)
            urls = _extract_urls(payload)
            status = _task_status(payload)
            if _is_terminal_failure(status):
                msg = (
                    payload.get("status_message")
                    or payload.get("message")
                    or payload.get("task_status_msg")
                    or str(payload)
                )
                raise KlingImageError(f"可灵任务失败: {msg}")
            if not urls:
                raise KlingImageError(f"任务完成但未解析到图片 URL: {payload!r:.500}")

        if not urls:
            raise KlingImageError(f"未解析到图片 URL，原始响应: {payload!r:.800}")

        return KlingImageResult(urls=urls, task_id=tid, model_name=self._model)

    async def _poll_task(self, task_id: str) -> dict[str, Any]:
        query_url = f"{self._base}{self._task_prefix}/{task_id}"
        deadline = monotonic() + self._poll_max
        last: dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            while monotonic() < deadline:
                resp = await client.get(query_url, headers=self._headers())
                if resp.status_code >= 400:
                    detail = resp.text[:2000]
                    raise KlingImageError(
                        f"查询任务 HTTP {resp.status_code}: {detail}",
                    )
                last = resp.json()
                raise_if_api_code_error(last)
                urls = _extract_urls(last)
                status = _task_status(last)
                if _is_terminal_success(status, urls):
                    return last
                if _is_terminal_failure(status):
                    return last
                await asyncio.sleep(self._poll_interval)
                logger.debug("kling poll task_id=%s status=%s", task_id, status)

        raise KlingImageError(f"轮询超时（{self._poll_max}s）task_id={task_id} last={last!r:.500}")
