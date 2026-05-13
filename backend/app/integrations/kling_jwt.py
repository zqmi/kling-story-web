"""可灵开放平台：Access Key + Secret Key 签发短期 JWT（Bearer）。

与 kling-story-pipeline-local/src/story_agent/integrations/kling_jwt.py 一致。
"""

from __future__ import annotations

import time

import jwt


def _strip_key(s: str) -> str:
    return s.strip().strip("\ufeff")


def build_kling_bearer_token(
    access_key: str,
    secret_key: str,
    *,
    ttl_seconds: int = 1800,
) -> str:
    ak = _strip_key(access_key)
    sk = _strip_key(secret_key)
    if not ak or not sk:
        raise ValueError("access_key 与 secret_key 不能为空")

    headers = {
        "alg": "HS256",
        "typ": "JWT",
    }
    now = int(time.time())
    ttl = min(max(60, int(ttl_seconds)), 1800)
    payload = {
        "iss": ak,
        "exp": now + ttl,
        "nbf": now - 5,
    }
    token = jwt.encode(payload, sk, algorithm="HS256", headers=headers)
    if isinstance(token, bytes):
        return token.decode("ascii")
    return token
