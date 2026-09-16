from __future__ import annotations

from pathlib import Path

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.models import SnapAnyPost, first_present
from video_fetcher.paths import extension_from_url, id_from_post_url, post_dir


def download_post(post: SnapAnyPost, settings: Settings) -> Path:
    """B站：只用 resource_url 下载成片；id 取 post_url 末节（BV 真 id）。

    实测 variants 内 video_url 为分片流且不可靠，不下载、不合并。
    """
    site = post.site
    post_url = post.post_url
    # 用户确认：post_url 最后一节即为 B 站真 id（如 BV…），写入目录与 manifest
    post_id = id_from_post_url(post_url)

    post.require_medias(site_label="Bilibili")
    video_media = post.require_video_media(site_label="Bilibili")

    resource_url = video_media.resource_url
    if not resource_url or not resource_url.strip():
        raise ValueError(
            "Bilibili video 媒体缺少 resource_url。"
            "本站不使用 variants.video_url（分片流实测不可靠）。"
        )
    resource_url = resource_url.strip()

    if not video_media.headers:
        raise ValueError(
            "Bilibili video 媒体缺少 headers（通常需 User-Agent 与 Referer），无法下载。"
        )

    video_ext = extension_from_url(resource_url, default="mp4")
    headers = video_media.headers

    out = post_dir(settings, site, post_id)
    video_name = f"{site}-{post_id}.{video_ext}"

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
    if video_media.preview_url and video_media.preview_url.strip():
        preview_url = video_media.preview_url.strip()
        cover_ext = extension_from_url(preview_url, default="jpg")
        if cover_ext == "bin":
            cover_ext = "jpg"
        preview_name = f"{site}-{post_id}.{cover_ext}"
        jobs.append(
            DownloadJob(
                key="preview",
                url=preview_url,
                dest=out / preview_name,
                headers=headers,
                required=False,
            )
        )

    results = download_parallel(jobs)
    preview_file = preview_name if results.get("preview") is not None else None

    write_manifest(
        out,
        build_manifest(
            site=site,
            id=post_id,
            title=post.title,
            text=post.text,
            created_at=post.manifest_created_at(),
            duration=first_present(post.duration, video_media.duration),
            post_url=post_url,
            preview_file=preview_file,
            video_file=video_name,
            subtitles_file=None,
        ),
    )
    return out
