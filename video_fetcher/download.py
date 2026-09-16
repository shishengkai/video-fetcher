from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from video_fetcher.http import get_session

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT = 120.0


class DownloadSizeError(RuntimeError):
    """下载完成但字节数与期望不符，可重试。"""


@dataclass(frozen=True)
class DownloadJob:
    """一次并行下载任务。

    required=False 时失败不抛错，结果中该 key 为 None（用于封面/字幕等可跳过资产）。
    """

    key: str
    url: str
    dest: Path
    headers: Mapping[str, str] | None = None
    expected_size: int | None = None
    required: bool = True
    timeout: float = DEFAULT_TIMEOUT
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


def download_file(
    url: str,
    dest: Path,
    *,
    headers: Mapping[str, str] | None = None,
    expected_size: int | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout: float = DEFAULT_TIMEOUT,
) -> Path:
    """下载到 dest；可选按字节数校验。网络错误与体积不符由 tenacity 重试。"""
    if not url:
        raise ValueError("下载 URL 为空。")

    req_headers = dict(headers or {})
    session = get_session()

    @retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_fixed(0.5),
        retry=retry_if_exception_type((requests.RequestException, DownloadSizeError, OSError)),
    )
    def _attempt() -> Path:
        try:
            return _download_once(
                session,
                url,
                dest,
                headers=req_headers,
                expected_size=expected_size,
                timeout=timeout,
            )
        except Exception:
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass
            raise

    try:
        return _attempt()
    except Exception as exc:  # noqa: BLE001 — 统一包装重试耗尽
        raise RuntimeError(
            f"下载失败（已重试 {max_attempts} 次）: {url}\n{exc}"
        ) from exc


def _download_once(
    session: requests.Session,
    url: str,
    dest: Path,
    *,
    headers: dict[str, str],
    expected_size: int | None,
    timeout: float,
) -> Path:
    with session.get(url, headers=headers, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            for chunk in response.iter_content(1 << 20):
                if chunk:
                    fh.write(chunk)

    actual = dest.stat().st_size
    if expected_size is not None and actual != int(expected_size):
        raise DownloadSizeError(
            f"下载大小校验失败：期望 {expected_size} 字节，实际 {actual} 字节；文件={dest}"
        )
    return dest


def download_parallel(
    jobs: list[DownloadJob],
    *,
    max_workers: int | None = None,
) -> dict[str, Path | None]:
    """同一任务内并行下载多个文件（媒体直链通常短时有效，需尽快同时拉取）。

    返回 key -> Path；可选任务失败时为 None。任一 required 任务失败则汇总后抛错。
    """
    if not jobs:
        return {}

    workers = max_workers or min(8, len(jobs))
    results: dict[str, Path | None] = {}
    errors: list[str] = []

    def _run(job: DownloadJob) -> tuple[str, Path | None, Exception | None]:
        try:
            path = download_file(
                job.url,
                job.dest,
                headers=job.headers,
                expected_size=job.expected_size,
                max_attempts=job.max_attempts,
                timeout=job.timeout,
            )
            return job.key, path, None
        except Exception as exc:  # noqa: BLE001
            if job.required:
                return job.key, None, exc
            return job.key, None, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run, job): job for job in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                key, path, err = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[job.key] = None
                if job.required:
                    errors.append(f"[{job.key}] {exc}")
                continue
            results[key] = path
            if err is not None:
                errors.append(f"[{key}] {err}")

    if errors:
        raise RuntimeError(
            "并行下载失败（至少一个必需文件未成功）：\n" + "\n".join(errors)
        )
    return results
