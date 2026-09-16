from __future__ import annotations

from pathlib import Path
from typing import Any

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.ffmpeg_merge import merge_av_copy
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.paths import extension_from_url, post_dir


def download_post(post: dict[str, Any], settings: Settings) -> Path:
    site = _require_str(post, "site")
    post_url = _require_str(post, "post_url")
    post_id = _require_str(post, "id")

    medias = post.get("medias")
    if not isinstance(medias, list) or not medias:
        raise ValueError("YouTube 结果缺少 medias 数组。")

    video_media = next(
        (m for m in medias if isinstance(m, dict) and m.get("media_type") == "video"),
        None,
    )
    if video_media is None:
        raise ValueError("YouTube 结果中未找到 media_type=video 的项。")

    variant = _pick_max_quality_variant(video_media)
    video_url = variant.get("video_url")
    if not isinstance(video_url, str) or not video_url.strip():
        raise ValueError(
            "所选 YouTube 变体缺少 video_url。"
            f"quality={variant.get('quality')!r}, quality_label={variant.get('quality_label')!r}"
        )
    video_url = video_url.strip()

    video_ext = variant.get("video_ext")
    if not isinstance(video_ext, str) or not video_ext.strip():
        video_ext = extension_from_url(video_url, default="mp4")
    else:
        video_ext = video_ext.strip()

    video_filesize = variant.get("video_filesize")
    expected_video = int(video_filesize) if video_filesize is not None else None

    audio_url_raw = variant.get("audio_url")
    has_separate_audio = isinstance(audio_url_raw, str) and bool(audio_url_raw.strip())
    audio_url = audio_url_raw.strip() if has_separate_audio else None

    headers = video_media.get("headers") if isinstance(video_media.get("headers"), dict) else {}

    out = post_dir(settings, site, post_id)
    video_name = f"{site}-{post_id}.{video_ext}"
    video_path = out / video_name

    jobs: list[DownloadJob] = [
        DownloadJob(
            key="video",
            url=video_url,
            dest=video_path,
            headers=headers,
            expected_size=expected_video,
            required=True,
        )
    ]

    audio_path: Path | None = None
    if has_separate_audio and audio_url is not None:
        audio_ext = variant.get("audio_ext")
        if not isinstance(audio_ext, str) or not audio_ext.strip():
            audio_ext = extension_from_url(audio_url, default="m4a")
        else:
            audio_ext = audio_ext.strip()
        audio_filesize = variant.get("audio_filesize")
        expected_audio = int(audio_filesize) if audio_filesize is not None else None
        audio_path = out / f"{site}-{post_id}.{audio_ext}"
        jobs.append(
            DownloadJob(
                key="audio",
                url=audio_url,
                dest=audio_path,
                headers=headers,
                expected_size=expected_audio,
                required=True,
            )
        )

    preview_name: str | None = None
    preview_url = video_media.get("preview_url")
    if isinstance(preview_url, str) and preview_url.strip():
        cover_ext = extension_from_url(preview_url, default="jpg")
        preview_name = f"{site}-{post_id}.{cover_ext}"
        jobs.append(
            DownloadJob(
                key="preview",
                url=preview_url.strip(),
                dest=out / preview_name,
                headers=headers,
                required=False,
            )
        )

    sub_name: str | None = None
    srt_url = _resolve_srt_url(post=post, video_media=video_media, variant=variant)
    if srt_url:
        sub_name = f"{site}-{post_id}.srt"
        jobs.append(
            DownloadJob(
                key="subtitles",
                url=srt_url,
                dest=out / sub_name,
                headers=headers,
                required=False,
            )
        )

    # 直链短时有效：视频/音频/封面/字幕尽量同一时刻开始拉取
    results = download_parallel(jobs)

    if has_separate_audio and audio_path is not None:
        merged_tmp = out / f"{site}-{post_id}.merged.{video_ext}"
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
    subtitles_file = sub_name if results.get("subtitles") is not None else None

    duration = _first_present(post.get("duration"), video_media.get("duration"), variant.get("duration"))
    created_at = post.get("created_at")
    if created_at is not None and not isinstance(created_at, (str, int, float)):
        created_at = str(created_at)

    write_manifest(
        out,
        build_manifest(
            site=site,
            id=post_id,
            title=post.get("title") if isinstance(post.get("title"), str) else None,
            text=post.get("text") if isinstance(post.get("text"), str) else None,
            created_at=created_at,
            duration=duration,
            post_url=post_url,
            preview_file=preview_file,
            video_file=video_name,
            subtitles_file=subtitles_file,
        ),
    )
    return out


def _pick_max_quality_variant(video_media: dict[str, Any]) -> dict[str, Any]:
    variants = video_media.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError("YouTube video 媒体缺少 variants，无法按 quality 选取。")
    dict_variants = [v for v in variants if isinstance(v, dict)]
    if not dict_variants:
        raise ValueError("YouTube variants 中没有任何对象项。")

    def quality_key(item: dict[str, Any]) -> int:
        raw = item.get("quality")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return -1

    best = max(dict_variants, key=quality_key)
    if quality_key(best) < 0:
        raise ValueError(
            "YouTube variants 均缺少可用 quality 数值。"
            f"摘要={[ {'quality': v.get('quality'), 'label': v.get('quality_label')} for v in dict_variants ]!r}"
        )
    return best


def _resolve_srt_url(
    *,
    post: dict[str, Any],
    video_media: dict[str, Any],
    variant: dict[str, Any],
) -> str | None:
    target_lang = _resolve_target_language_tag(post, variant)
    if not target_lang:
        return None

    subtitles = video_media.get("subtitles")
    if not isinstance(subtitles, list) or not subtitles:
        return None

    matched = _match_subtitle_entry(subtitles, target_lang)
    if matched is None:
        return None

    urls = matched.get("urls")
    if not isinstance(urls, list):
        return None
    for item in urls:
        if isinstance(item, dict) and item.get("format") == "srt":
            raw = item.get("url")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _resolve_target_language_tag(post: dict[str, Any], variant: dict[str, Any]) -> str | None:
    tag = variant.get("language_tag")
    if isinstance(tag, str) and tag.strip():
        return tag.strip()

    medias = post.get("medias")
    if not isinstance(medias, list):
        return None
    audio_media = next(
        (m for m in medias if isinstance(m, dict) and m.get("media_type") == "audio"),
        None,
    )
    if audio_media is None:
        return None
    variants = audio_media.get("variants")
    if not isinstance(variants, list):
        return None
    for item in variants:
        if isinstance(item, dict) and item.get("is_default") is True:
            t = item.get("language_tag")
            if isinstance(t, str) and t.strip():
                return t.strip()
    return None


def _match_subtitle_entry(subtitles: list[Any], target_lang: str) -> dict[str, Any] | None:
    target_norm = target_lang.strip().lower()
    target_primary = _primary_lang(target_norm)

    for item in subtitles:
        if not isinstance(item, dict):
            continue
        tag = item.get("language_tag")
        if isinstance(tag, str) and tag.strip().lower() == target_norm:
            return item

    for item in subtitles:
        if not isinstance(item, dict):
            continue
        tag = item.get("language_tag")
        if isinstance(tag, str) and _primary_lang(tag) == target_primary:
            return item
    return None


def _primary_lang(tag: str) -> str:
    text = tag.strip().lower().replace("_", "-")
    return text.split("-", 1)[0]


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
        raise ValueError(f"YouTube 结果缺少或无效字段 {key!r}。顶层键={list(data.keys())}")
    return value.strip()
