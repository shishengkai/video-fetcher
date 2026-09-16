from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from video_fetcher.config import Settings
from video_fetcher.download import download_file
from video_fetcher.paths import extension_from_url, post_dir

_CST = timezone(timedelta(hours=8))
_ORIGINAL_LABELS = {"original", "origianl"}  # 含设想稿中的拼写


def download_post(post: dict[str, Any], settings: Settings) -> Path:
    site = _require_str(post, "site")
    post_id = _require_str(post, "id")
    text = post.get("text") if isinstance(post.get("text"), str) else ""
    post_url = _require_str(post, "post_url")
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

    variant, pick_reason = _pick_video_variant(video_media)
    video_url = variant.get("video_url")
    if not isinstance(video_url, str) or not video_url:
        raise ValueError(f"所选变体缺少 video_url（{pick_reason}）。")
    video_ext = variant.get("video_ext")
    if not isinstance(video_ext, str) or not video_ext:
        raise ValueError(f"所选变体缺少 video_ext（{pick_reason}）。")
    video_filesize = variant.get("video_filesize")
    if video_filesize is None:
        raise ValueError(f"所选变体缺少 video_filesize（{pick_reason}）。")

    preview_url = video_media.get("preview_url")
    if not isinstance(preview_url, str) or not preview_url:
        raise ValueError("video 媒体缺少 preview_url（封面）。")

    headers = video_media.get("headers") if isinstance(video_media.get("headers"), dict) else {}

    out = post_dir(settings, site, post_id)
    video_name = f"{site}-{post_id}.{video_ext}"
    cover_ext = extension_from_url(preview_url, default="jpg")
    cover_name = f"{site}-{post_id}.{cover_ext}"
    info_name = f"{site}-{post_id}.md"

    video_path = out / video_name
    cover_path = out / cover_name
    info_path = out / info_name

    # 视频：失败重试 3 次后抛错中止（核心产物）
    download_file(
        video_url,
        video_path,
        headers=headers,
        expected_size=int(video_filesize),
    )

    # 封面：失败则记录进 md，不阻断主流程
    cover_ok = True
    cover_error = ""
    try:
        download_file(preview_url, cover_path, headers=headers)
    except Exception as exc:  # noqa: BLE001
        cover_ok = False
        cover_error = str(exc)

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
        ),
        encoding="utf-8",
    )
    return out


def _pick_video_variant(video_media: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """优先 Original；不存在则取 quality 数值最高的变体。"""
    variants = video_media.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError(
            "抖音 video 媒体缺少 variants；无法选取下载画质。"
            "（若该帖只有 resource_url 而无 variants，需迭代规则。）"
        )

    dict_variants = [v for v in variants if isinstance(v, dict)]
    if not dict_variants:
        raise ValueError("抖音 variants 中没有任何对象项。")

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
            "无 Original 变体，且所有变体都缺少可用的 quality 数值，无法回退选取。"
            f"variants 摘要={_variants_summary(dict_variants)!r}"
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
) -> str:
    cover_line = (
        f"[封面](./{cover_name})"
        if cover_name
        else f"（封面下载失败）{cover_error}"
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
        f"## 下载结果\n\n"
        f"{cover_line}\n\n"
        f"[视频](./{video_name})\n"
    )


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"抖音结果缺少或无效字段 {key!r}。顶层键={list(data.keys())}")
    return value.strip()
