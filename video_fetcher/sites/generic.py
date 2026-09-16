from __future__ import annotations

from pathlib import Path
from typing import Any

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.ffmpeg_merge import merge_av_copy
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.models import Media, SnapAnyPost, first_present
from video_fetcher.paths import extension_from_url, id_from_post_url, post_dir
from video_fetcher.quality import pick_variant_by_quality

_IMAGE_TYPES = frozenset({"photo", "image", "images", "pic", "picture"})


def download_post(post: SnapAnyPost, settings: Settings) -> Path:
    """未定制站点的通用下载：按 SnapAny 文档字段 + 本项目品质/并行约定。

    - 优先 video 媒体：resource_url → 否则 variants（≤1080，分离音轨则合并）
    - 无 video 时：下载全部带 resource_url 的图片类媒体
    - 有 headers 则原样带上（SnapAny 文档要求）
    - 目录 id：接口 id，否则 post_url 末节；manifest.id 仅写接口真 id
    """
    site = post.site
    post_url = post.post_url
    dir_id, api_id = _resolve_ids(post)

    medias = post.require_medias(site_label=f"通用下载器({site})")
    video_media = post.media_by_type("video")

    out = post_dir(settings, site, dir_id)

    if video_media is not None:
        return _download_video_post(
            post=post,
            site=site,
            post_url=post_url,
            dir_id=dir_id,
            api_id=api_id,
            video_media=video_media,
            out=out,
        )

    image_medias = [
        m
        for m in medias
        if (m.media_type or "").lower() in _IMAGE_TYPES
        and m.resource_url
        and m.resource_url.strip()
    ]
    if image_medias:
        return _download_image_post(
            post=post,
            site=site,
            post_url=post_url,
            dir_id=dir_id,
            api_id=api_id,
            image_medias=image_medias,
            out=out,
        )

    # 最后尝试：任意带 resource_url 的媒体当作主文件
    for media in medias:
        if media.resource_url and media.resource_url.strip():
            return _download_single_resource(
                post=post,
                site=site,
                post_url=post_url,
                dir_id=dir_id,
                api_id=api_id,
                media=media,
                out=out,
            )

    types = [m.media_type for m in medias]
    raise ValueError(
        f"通用下载器无法处理 site={site!r}：medias 中无可用 video/图片/resource_url。"
        f"media_type 列表={types!r}"
    )


def _resolve_ids(post: SnapAnyPost) -> tuple[str, str | None]:
    api_id = post.api_id()
    if api_id:
        return api_id, api_id
    return id_from_post_url(post.post_url), None


def _download_video_post(
    *,
    post: SnapAnyPost,
    site: str,
    post_url: str,
    dir_id: str,
    api_id: str | None,
    video_media: Media,
    out: Path,
) -> Path:
    source = _resolve_video_source(video_media)
    headers = video_media.headers or None

    video_name = f"{site}-{dir_id}.{source['video_ext']}"
    video_path = out / video_name

    jobs: list[DownloadJob] = [
        DownloadJob(
            key="video",
            url=source["video_url"],
            dest=video_path,
            headers=headers,
            expected_size=source.get("video_filesize"),
            required=True,
        )
    ]

    audio_path: Path | None = None
    audio_url = source.get("audio_url")
    if isinstance(audio_url, str) and audio_url.strip():
        audio_ext = source.get("audio_ext") or extension_from_url(audio_url, default="m4a")
        audio_path = out / f"{site}-{dir_id}.{audio_ext}"
        jobs.append(
            DownloadJob(
                key="audio",
                url=audio_url.strip(),
                dest=audio_path,
                headers=headers,
                expected_size=source.get("audio_filesize"),
                required=True,
            )
        )

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

    if audio_path is not None:
        merged_tmp = out / f"{site}-{dir_id}.merged.{source['video_ext']}"
        try:
            merge_av_copy(video_path, audio_path, merged_tmp)
            merged_tmp.replace(video_path)
        finally:
            if merged_tmp.exists():
                try:
                    merged_tmp.unlink()
                except OSError:
                    pass
            if audio_path.exists():
                try:
                    audio_path.unlink()
                except OSError:
                    pass

    preview_file = preview_name if results.get("preview") is not None else None

    write_manifest(
        out,
        build_manifest(
            site=site,
            id=api_id,
            title=post.title,
            text=post.text,
            created_at=post.manifest_created_at(),
            duration=first_present(post.duration, video_media.duration, source.get("duration")),
            post_url=post_url,
            preview_file=preview_file,
            video_file=video_name,
            subtitles_file=None,
        ),
    )
    return out


def _resolve_video_source(video_media: Media) -> dict[str, Any]:
    """返回下载所需字段字典。

    优先 resource_url；不可用时再按项目品质规则从 variants 选取（分离音轨则带上）。
    """
    resource_url = video_media.resource_url
    if isinstance(resource_url, str) and resource_url.strip():
        resource_url = resource_url.strip()
        return {
            "video_url": resource_url,
            "video_ext": extension_from_url(resource_url, default="mp4"),
            "duration": video_media.duration,
        }

    if video_media.variants:
        try:
            variant, _reason = pick_variant_by_quality(video_media.variants)
        except ValueError:
            variant = None
        else:
            video_url = variant.get("video_url")
            if isinstance(video_url, str) and video_url.strip():
                video_url = video_url.strip()
                video_ext = variant.get("video_ext")
                if not isinstance(video_ext, str) or not video_ext.strip():
                    video_ext = extension_from_url(video_url, default="mp4")
                else:
                    video_ext = video_ext.strip()

                result: dict[str, Any] = {
                    "video_url": video_url,
                    "video_ext": video_ext,
                    "duration": variant.get("duration"),
                }
                filesize = variant.get("video_filesize")
                if filesize is not None:
                    try:
                        size_i = int(filesize)
                        if size_i > 0:
                            result["video_filesize"] = size_i
                    except (TypeError, ValueError):
                        pass

                audio_url = variant.get("audio_url")
                if isinstance(audio_url, str) and audio_url.strip():
                    result["audio_url"] = audio_url.strip()
                    audio_ext = variant.get("audio_ext")
                    if isinstance(audio_ext, str) and audio_ext.strip():
                        result["audio_ext"] = audio_ext.strip()
                    else:
                        result["audio_ext"] = extension_from_url(
                            result["audio_url"], default="m4a"
                        )
                    audio_size = variant.get("audio_filesize")
                    if audio_size is not None:
                        try:
                            a_i = int(audio_size)
                            if a_i > 0:
                                result["audio_filesize"] = a_i
                        except (TypeError, ValueError):
                            pass
                return result

    raise ValueError(
        "通用下载器：video 媒体既无 resource_url，也无可用 variants.video_url。"
    )


def _download_image_post(
    *,
    post: SnapAnyPost,
    site: str,
    post_url: str,
    dir_id: str,
    api_id: str | None,
    image_medias: list[Media],
    out: Path,
) -> Path:
    headers = image_medias[0].headers or None
    jobs: list[DownloadJob] = []
    names: list[str] = []

    for index, media in enumerate(image_medias, start=1):
        url = media.resource_url
        assert url is not None
        url = url.strip()
        ext = extension_from_url(url, default="jpg")
        if ext == "bin":
            ext = "jpg"
        name = f"{site}-{dir_id}-{index}.{ext}"
        names.append(name)
        jobs.append(
            DownloadJob(
                key=f"image-{index}",
                url=url,
                dest=out / name,
                headers=media.headers or headers,
                required=True,
            )
        )

    download_parallel(jobs)

    # manifest 主文件用第一张；其余文件同目录可被下游列举
    write_manifest(
        out,
        build_manifest(
            site=site,
            id=api_id,
            title=post.title,
            text=post.text,
            created_at=post.manifest_created_at(),
            duration=post.duration,
            post_url=post_url,
            preview_file=names[0],
            video_file=names[0],
            subtitles_file=None,
        ),
    )
    return out


def _download_single_resource(
    *,
    post: SnapAnyPost,
    site: str,
    post_url: str,
    dir_id: str,
    api_id: str | None,
    media: Media,
    out: Path,
) -> Path:
    url = media.resource_url
    assert url is not None
    url = url.strip()
    headers = media.headers or None
    ext = extension_from_url(url, default="bin")
    name = f"{site}-{dir_id}.{ext}"

    download_parallel(
        [
            DownloadJob(
                key="main",
                url=url,
                dest=out / name,
                headers=headers,
                required=True,
            )
        ]
    )

    write_manifest(
        out,
        build_manifest(
            site=site,
            id=api_id,
            title=post.title,
            text=post.text,
            created_at=post.manifest_created_at(),
            duration=first_present(post.duration, media.duration),
            post_url=post_url,
            preview_file=None,
            video_file=name,
            subtitles_file=None,
        ),
    )
    return out
