from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from video_fetcher.config import Settings
from video_fetcher.download import download_file
from video_fetcher.paths import extension_from_url, id_from_post_url, post_dir

_CST = timezone(timedelta(hours=8))
_ORIGINAL_LABELS = {"original", "origianl"}  # 含设想稿中的拼写


def download_post(post: dict[str, Any], settings: Settings) -> Path:
    site = _require_str(post, "site")
    post_url = _require_str(post, "post_url")
    post_id = _resolve_post_id(post, post_url)
    text = post.get("text") if isinstance(post.get("text"), str) else ""
    created_at_raw = post.get("created_at")

    medias = post.get("medias")
    if not isinstance(medias, list) or not medias:
        raise ValueError("抖音结果缺少 medias 数组。")

    video_media = next(
        (m for m in medias if isinstance(m, dict) and m.get("media_type") == "video"),
        None,
    )
    if video_media is None:
        raise ValueError("抖音结果中未找到 media_type=video 的项。")

    video_url, video_ext, video_filesize, pick_reason = _resolve_video_source(video_media)

    headers = video_media.get("headers") if isinstance(video_media.get("headers"), dict) else {}

    out = post_dir(settings, site, post_id)
    video_name = f"{site}-{post_id}.{video_ext}"
    info_name = f"{site}-{post_id}.md"
    video_path = out / video_name
    info_path = out / info_name

    expected = int(video_filesize) if video_filesize is not None else None
    download_file(
        video_url,
        video_path,
        headers=headers,
        expected_size=expected,
    )

    cover_name: str | None = None
    cover_ok = False
    cover_error = ""
    preview_url = video_media.get("preview_url")
    if isinstance(preview_url, str) and preview_url.strip():
        cover_ext = extension_from_url(preview_url, default="jpg")
        cover_name = f"{site}-{post_id}.{cover_ext}"
        cover_path = out / cover_name
        try:
            download_file(preview_url.strip(), cover_path, headers=headers)
            cover_ok = True
        except Exception as exc:  # noqa: BLE001
            cover_error = str(exc)
            cover_name = None
    else:
        cover_error = "缺少 preview_url，已跳过封面"

    published = _format_beijing_time(created_at_raw)
    info_path.write_text(
        _render_info_md(
            site=site,
            post_id=post_id,
            text=text,
            published=published,
            post_url=post_url,
            cover_name=cover_name if cover_ok else None,
            video_name=video_name,
            cover_error=cover_error,
            pick_reason=pick_reason,
        ),
        encoding="utf-8",
    )
    return out


def _resolve_post_id(post: dict[str, Any], post_url: str) -> str:
    raw = post.get("id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if raw is not None and not isinstance(raw, str):
        # 偶发数字 id
        text = str(raw).strip()
        if text:
            return text
    return id_from_post_url(post_url)


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


def _format_beijing_time(raw: Any) -> str:
    if raw is None or raw == "":
        return "（无 created_at）"
    try:
        ts = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"created_at 不是可解析的时间戳: {raw!r}") from exc
    return datetime.fromtimestamp(ts, tz=_CST).strftime("%Y-%m-%d %H:%M:%S")


def _render_info_md(
    *,
    site: str,
    post_id: str,
    text: str,
    published: str,
    post_url: str,
    cover_name: str | None,
    video_name: str,
    cover_error: str,
    pick_reason: str,
) -> str:
    cover_line = (
        f"[封面](./{cover_name})"
        if cover_name
        else f"（封面未保存）{cover_error}"
    )
    return (
        f"# {site}-{post_id}\n\n"
        f"## 描述\n\n"
        f"{text}\n\n"
        f"## 发布时间\n\n"
        f"{published}\n\n"
        f"## 源链接\n\n"
        f"{post_url}\n\n"
        f"## id\n\n"
        f"{site} {post_id}\n\n"
        f"## 下载选取\n\n"
        f"{pick_reason}\n\n"
        f"## 下载结果\n\n"
        f"{cover_line}\n\n"
        f"[视频](./{video_name})\n"
    )


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"抖音结果缺少或无效字段 {key!r}。顶层键={list(data.keys())}")
    return value.strip()
