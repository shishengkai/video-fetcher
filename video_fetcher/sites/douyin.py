from __future__ import annotations

from pathlib import Path

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.models import Media, SnapAnyPost, first_present
from video_fetcher.paths import extension_from_url, id_from_post_url, post_dir
from video_fetcher.quality import pick_variant_by_quality


def download_post(post: SnapAnyPost, settings: Settings) -> Path:
    site = post.site
    post_url = post.post_url
    dir_id, api_id = _resolve_post_id(post)

    post.require_medias(site_label="抖音")
    video_media = post.require_video_media(site_label="抖音")

    video_url, video_ext, video_filesize, _pick_reason = _resolve_video_source(video_media)
    headers = video_media.headers

    out = post_dir(settings, site, dir_id)
    video_name = f"{site}-{dir_id}.{video_ext}"
    video_path = out / video_name

    expected = int(video_filesize) if video_filesize is not None else None
    jobs = [
        DownloadJob(
            key="video",
            url=video_url,
            dest=video_path,
            headers=headers,
            expected_size=expected,
            required=True,
        )
    ]

    preview_name: str | None = None
    if video_media.preview_url and video_media.preview_url.strip():
        preview_url = video_media.preview_url.strip()
        cover_ext = extension_from_url(preview_url, default="jpg")
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


def _resolve_post_id(post: SnapAnyPost) -> tuple[str, str | None]:
    """返回 (目录用 id, manifest 用真 id|None)。"""
    api_id = post.api_id()
    if api_id:
        return api_id, api_id
    return id_from_post_url(post.post_url), None


def _resolve_video_source(
    video_media: Media,
) -> tuple[str, str, int | None, str]:
    """返回 (video_url, video_ext, video_filesize|None, pick_reason)。

    优先级：按 ≤1080 最大 / >1080 最小选 variants → resource_url。
    变体缺 ext / filesize 时软回退；变体不可用时再回退 resource_url。
    """
    if video_media.variants:
        try:
            variant, pick_reason = pick_variant_by_quality(video_media.variants)
        except ValueError as exc:
            resource = _resource_url_fallback(video_media, why=f"variants 不可用（{exc}）")
            if resource is not None:
                return resource
            raise

        video_url = variant.get("video_url")
        if isinstance(video_url, str) and video_url.strip():
            video_url = video_url.strip()
            ext_raw = variant.get("video_ext")
            if isinstance(ext_raw, str) and ext_raw.strip():
                video_ext = ext_raw.strip()
            else:
                video_ext = extension_from_url(video_url, default="mp4")
                pick_reason = f"{pick_reason}；缺 video_ext，已从 URL 推断为 {video_ext!r}"

            filesize_raw = variant.get("video_filesize")
            if filesize_raw is None:
                filesize = None
                pick_reason = f"{pick_reason}；缺 video_filesize，跳过字节校验"
            else:
                filesize = int(filesize_raw)
            return video_url, video_ext, filesize, pick_reason

        resource = _resource_url_fallback(
            video_media,
            why=f"所选变体缺少 video_url（{pick_reason}）",
        )
        if resource is not None:
            return resource
        raise ValueError(f"所选变体缺少 video_url（{pick_reason}），且无 resource_url。")

    resource = _resource_url_fallback(video_media, why="无 variants")
    if resource is not None:
        return resource
    raise ValueError(
        "抖音 video 媒体既无可用 variants，也无 resource_url，无法下载视频。"
    )


def _resource_url_fallback(
    video_media: Media,
    *,
    why: str,
) -> tuple[str, str, int | None, str] | None:
    resource_url = video_media.resource_url
    if not resource_url or not resource_url.strip():
        return None
    ext = extension_from_url(resource_url, default="mp4")
    return (
        resource_url.strip(),
        ext,
        None,
        f"{why}，回退 resource_url（跳过 filesize 校验）",
    )
