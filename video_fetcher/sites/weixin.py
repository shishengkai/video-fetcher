from __future__ import annotations

from pathlib import Path
from typing import Any

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.paths import extension_from_url, id_from_post_url, post_dir


def download_post(post: dict[str, Any], settings: Settings) -> Path:
    site = _require_str(post, "site")
    post_url = _require_str(post, "post_url")
    # 微信视频号：目录 id 固定取自 post_url 最后一节；manifest 的 id 仅在接口有真 id 时写入
    dir_id = id_from_post_url(post_url)
    api_id = _api_id_or_none(post)

    medias = post.get("medias")
    if not isinstance(medias, list) or not medias:
        raise ValueError("微信视频号结果缺少 medias 数组。")

    video_media = next(
        (m for m in medias if isinstance(m, dict) and m.get("media_type") == "video"),
        None,
    )
    if video_media is None:
        # 样例无 media_type 时，退回第一项
        video_media = medias[0] if isinstance(medias[0], dict) else None
    if video_media is None:
        raise ValueError("微信视频号结果中未找到可用的 video 媒体项。")

    resource_url = video_media.get("resource_url")
    if not isinstance(resource_url, str) or not resource_url.strip():
        raise ValueError("微信视频号 video 媒体缺少 resource_url。")
    resource_url = resource_url.strip()

    video_ext = extension_from_url(resource_url, default="mp4")
    headers = video_media.get("headers") if isinstance(video_media.get("headers"), dict) else {}

    out = post_dir(settings, site, dir_id)
    video_name = f"{site}-{dir_id}.{video_ext}"

    jobs = [
        DownloadJob(
            key="video",
            url=resource_url,
            dest=out / video_name,
            headers=headers,
            required=True,
        )
    ]

    preview_name: str | None = None
    preview_url = video_media.get("preview_url")
    if isinstance(preview_url, str) and preview_url.strip():
        cover_ext = extension_from_url(preview_url, default="jpg")
        if cover_ext == "bin":
            cover_ext = "jpg"
        preview_name = f"{site}-{dir_id}.{cover_ext}"
        jobs.append(
            DownloadJob(
                key="preview",
                url=preview_url.strip(),
                dest=out / preview_name,
                headers=headers,
                required=False,
            )
        )

    results = download_parallel(jobs)
    preview_file = preview_name if results.get("preview") is not None else None

    duration = _first_present(post.get("duration"), video_media.get("duration"))
    created_at = post.get("created_at")
    if created_at is not None and not isinstance(created_at, (str, int, float)):
        created_at = str(created_at)

    write_manifest(
        out,
        build_manifest(
            site=site,
            id=api_id,
            title=post.get("title") if isinstance(post.get("title"), str) else None,
            text=post.get("text") if isinstance(post.get("text"), str) else None,
            created_at=created_at,
            duration=duration,
            post_url=post_url,
            preview_file=preview_file,
            video_file=video_name,
            subtitles_file=None,
        ),
    )
    return out


def _api_id_or_none(post: dict[str, Any]) -> str | None:
    raw = post.get("id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if raw is not None and not isinstance(raw, str):
        text = str(raw).strip()
        if text:
            return text
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"微信视频号结果缺少或无效字段 {key!r}。顶层键={list(data.keys())}")
    return value.strip()
