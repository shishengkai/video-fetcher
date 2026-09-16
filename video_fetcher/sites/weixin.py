from __future__ import annotations

from pathlib import Path

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.models import SnapAnyPost, first_present
from video_fetcher.paths import extension_from_url, id_from_post_url, post_dir


def download_post(post: SnapAnyPost, settings: Settings) -> Path:
    site = post.site
    post_url = post.post_url
    # 微信视频号：目录 id 固定取自 post_url 最后一节；manifest 的 id 仅在接口有真 id 时写入
    dir_id = id_from_post_url(post_url)
    api_id = post.api_id()

    medias = post.require_medias(site_label="微信视频号")
    video_media = post.media_by_type("video")
    if video_media is None:
        # 样例无 media_type 时，退回第一项（业务软回退，暂保留）
        video_media = medias[0]
    if video_media is None:
        raise ValueError("微信视频号结果中未找到可用的 video 媒体项。")

    resource_url = video_media.resource_url
    if not resource_url or not resource_url.strip():
        raise ValueError("微信视频号 video 媒体缺少 resource_url。")
    resource_url = resource_url.strip()

    video_ext = extension_from_url(resource_url, default="mp4")
    headers = video_media.headers

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
    if video_media.preview_url and video_media.preview_url.strip():
        preview_url = video_media.preview_url.strip()
        cover_ext = extension_from_url(preview_url, default="jpg")
        if cover_ext == "bin":
            cover_ext = "jpg"
        preview_name = f"{site}-{dir_id}.{cover_ext}"
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
            id=api_id,
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
