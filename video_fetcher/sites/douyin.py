from __future__ import annotations

from pathlib import Path
from typing import Any

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.paths import extension_from_url, id_from_post_url, post_dir

_ORIGINAL_LABELS = {"original", "origianl"}  # 含设想稿中的拼写


def download_post(post: dict[str, Any], settings: Settings) -> Path:
    site = _require_str(post, "site")
    post_url = _require_str(post, "post_url")
    dir_id, api_id = _resolve_post_id(post, post_url)

    medias = post.get("medias")
    if not isinstance(medias, list) or not medias:
        raise ValueError("抖音结果缺少 medias 数组。")

    video_media = next(
        (m for m in medias if isinstance(m, dict) and m.get("media_type") == "video"),
        None,
    )
    if video_media is None:
        raise ValueError("抖音结果中未找到 media_type=video 的项。")

    video_url, video_ext, video_filesize, _pick_reason = _resolve_video_source(video_media)
    headers = video_media.get("headers") if isinstance(video_media.get("headers"), dict) else {}

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
    preview_url = video_media.get("preview_url")
    if isinstance(preview_url, str) and preview_url.strip():
        cover_ext = extension_from_url(preview_url, default="jpg")
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


def _resolve_post_id(post: dict[str, Any], post_url: str) -> tuple[str, str | None]:
    """返回 (目录用 id, manifest 用真 id|None)。

    仅接口返回的 id 写入 manifest；由 post_url 回退造出的 id 只用于目录名。
    """
    raw = post.get("id")
    if isinstance(raw, str) and raw.strip():
        value = raw.strip()
        return value, value
    if raw is not None and not isinstance(raw, str):
        text = str(raw).strip()
        if text:
            return text, text
    return id_from_post_url(post_url), None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _resolve_video_source(
    video_media: dict[str, Any],
) -> tuple[str, str, int | None, str]:
    """返回 (video_url, video_ext, video_filesize|None, pick_reason)。

    优先级：Original → 最高 quality → resource_url。
    变体缺 ext / filesize 时软回退；变体不可用时再回退 resource_url。
    """
    variants = video_media.get("variants")
    if isinstance(variants, list) and variants:
        try:
            variant, pick_reason = _pick_video_variant(variants)
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

            filesize: int | None
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
    video_media: dict[str, Any],
    *,
    why: str,
) -> tuple[str, str, int | None, str] | None:
    resource_url = video_media.get("resource_url")
    if not isinstance(resource_url, str) or not resource_url.strip():
        return None
    ext = extension_from_url(resource_url, default="mp4")
    return (
        resource_url.strip(),
        ext,
        None,
        f"{why}，回退 resource_url（跳过 filesize 校验）",
    )


def _pick_video_variant(variants: list[Any]) -> tuple[dict[str, Any], str]:
    """优先 Original；不存在则取 quality 数值最高的变体。"""
    dict_variants = [v for v in variants if isinstance(v, dict)]
    if not dict_variants:
        raise ValueError("variants 中没有任何对象项")

    for item in dict_variants:
        label = item.get("quality_label")
        if isinstance(label, str) and label.strip().lower() in _ORIGINAL_LABELS:
            return item, f"quality_label={label!r}"

    def quality_key(item: dict[str, Any]) -> int:
        raw = item.get("quality")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return -1

    best = max(dict_variants, key=quality_key)
    if quality_key(best) < 0:
        raise ValueError(
            "无 Original 且无可用 quality；"
            f"摘要={_variants_summary(dict_variants)!r}"
        )
    label = best.get("quality_label")
    return (
        best,
        f"无 Original，回退 quality 最高："
        f"quality={best.get('quality')!r}, quality_label={label!r}",
    )


def _variants_summary(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "quality": v.get("quality"),
            "quality_label": v.get("quality_label"),
            "has_video_url": bool(v.get("video_url")),
        }
        for v in variants
    ]


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"抖音结果缺少或无效字段 {key!r}。顶层键={list(data.keys())}")
    return value.strip()
