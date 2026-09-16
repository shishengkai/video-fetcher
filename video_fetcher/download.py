from __future__ import annotations

from pathlib import Path
from typing import Mapping

import requests

DEFAULT_MAX_ATTEMPTS = 3


def download_file(
    url: str,
    dest: Path,
    *,
    headers: Mapping[str, str] | None = None,
    expected_size: int | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout: float = 120.0,
) -> Path:
    """下载到 dest；可选按字节数校验，失败最多重试 max_attempts 次。

    若仍失败：抛出最后一次错误（调用方可决定跳过或中止）。
    """
    if not url:
        raise ValueError("下载 URL 为空。")

    req_headers = dict(headers or {})
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            with requests.get(
                url,
                headers=req_headers,
                stream=True,
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as fh:
                    for chunk in response.iter_content(1 << 20):
                        if chunk:
                            fh.write(chunk)

            actual = dest.stat().st_size
            if expected_size is not None and actual != int(expected_size):
                raise RuntimeError(
                    f"下载大小校验失败（第 {attempt}/{max_attempts} 次）："
                    f"期望 {expected_size} 字节，实际 {actual} 字节；文件={dest}"
                )
            return dest
        except Exception as exc:  # noqa: BLE001 — 汇总重试
            last_error = exc
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass
            if attempt >= max_attempts:
                break

    assert last_error is not None
    raise RuntimeError(
        f"下载失败（已重试 {max_attempts} 次）: {url}\n{last_error}"
    ) from last_error
