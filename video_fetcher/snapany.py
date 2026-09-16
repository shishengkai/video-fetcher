from __future__ import annotations

import json
import time
from typing import Any

import requests

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
    """调用 SnapAny extract/post；失败最多重试 max_attempts 次后抛出完整错误含义。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept-Language": "zh",
        "Content-Type": "application/json",
    }
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return _extract_once(url, headers=headers, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 — 统一重试网络与 API 业务失败
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(retry_delay_sec)

    assert last_error is not None
    raise RuntimeError(
        f"SnapAny 提取失败（已重试 {max_attempts} 次）：\n{last_error}"
    ) from last_error


def _extract_once(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    try:
        response = requests.post(
            SNAPANY_EXTRACT_URL,
            headers=headers,
            json={"url": url},
            timeout=timeout,
        )
    except requests.RequestException as exc:
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
