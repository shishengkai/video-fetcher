from __future__ import annotations

import json
from typing import Any

import requests

SNAPANY_EXTRACT_URL = "https://api.snapany.com/openapi/v1/extract/post"


def extract_post(url: str, api_key: str, timeout: float = 60.0) -> dict[str, Any]:
    """调用 SnapAny extract/post；失败时抛出含完整响应含义的错误。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept-Language": "zh",
        "Content-Type": "application/json",
    }
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
