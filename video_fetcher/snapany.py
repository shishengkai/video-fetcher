from __future__ import annotations

import json
from typing import Any

from tenacity import retry, stop_after_attempt, wait_fixed

from video_fetcher.http import get_session

SNAPANY_EXTRACT_URL = "https://api.snapany.com/openapi/v1/extract/post"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SEC = 1.0


def extract_post(
    url: str,
    api_key: str,
    *,
    timeout: float = 60.0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay_sec: float = DEFAULT_RETRY_DELAY_SEC,
) -> dict[str, Any]:
    """调用 SnapAny extract/post；失败由 tenacity 重试后抛出完整错误含义。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept-Language": "zh",
        "Content-Type": "application/json",
    }

    @retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_fixed(retry_delay_sec),
    )
    def _attempt() -> dict[str, Any]:
        return _extract_once(url, headers=headers, timeout=timeout)

    try:
        return _attempt()
    except Exception as exc:  # noqa: BLE001 — 统一包装重试耗尽
        raise RuntimeError(
            f"SnapAny 提取失败（已重试 {max_attempts} 次）：\n{exc}"
        ) from exc


def _extract_once(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    session = get_session()
    try:
        response = session.post(
            SNAPANY_EXTRACT_URL,
            headers=headers,
            json={"url": url},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — 交 tenacity / Session 重试
        raise RuntimeError(f"SnapAny 请求失败（网络错误）: {exc}") from exc

    body_text = response.text
    try:
        body = response.json()
    except ValueError:
        body = None

    if response.ok and isinstance(body, dict):
        return body

    detail = body_text
    if isinstance(body, dict):
        detail = json.dumps(body, ensure_ascii=False, indent=2)
    raise RuntimeError(
        "SnapAny API 错误：\n"
        f"HTTP {response.status_code}\n"
        f"{detail}"
    )
