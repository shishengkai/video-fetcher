from __future__ import annotations

from pathlib import Path
from typing import Any

from video_fetcher.config import Settings
from video_fetcher.download import DownloadJob, download_parallel
from video_fetcher.ffmpeg_merge import merge_av_copy
from video_fetcher.manifest import build_manifest, write_manifest
from video_fetcher.models import Media, SnapAnyPost, Subtitle, first_present
from video_fetcher.paths import extension_from_url, post_dir
from video_fetcher.quality import pick_audio_variant, pick_variant_by_quality


def download_post(post: SnapAnyPost, settings: Settings) -> Path:
    site = post.site
    post_url = post.post_url
    post_id = post.require_api_id()

    post.require_medias(site_label="YouTube")
    video_media = post.require_video_media(site_label="YouTube")

    variant = _pick_video_variant(video_media)
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

    audio_pick = _resolve_separate_audio(post=post, video_variant=variant)
    has_separate_audio = audio_pick is not None
    audio_url = audio_pick[0] if audio_pick else None
    audio_ext = audio_pick[1] if audio_pick else None
    expected_audio = audio_pick[2] if audio_pick else None

    headers = video_media.headers

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
    if has_separate_audio and audio_url is not None and audio_ext is not None:
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
    if video_media.preview_url and video_media.preview_url.strip():
        preview_url = video_media.preview_url.strip()
        cover_ext = extension_from_url(preview_url, default="jpg")
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

    write_manifest(
        out,
        build_manifest(
            site=site,
            id=post_id,
            title=post.title,
            text=post.text,
            created_at=post.manifest_created_at(),
            duration=first_present(post.duration, video_media.duration, variant.get("duration")),
            post_url=post_url,
            preview_file=preview_file,
            video_file=video_name,
            subtitles_file=subtitles_file,
        ),
    )
    return out


def _pick_video_variant(video_media: Media) -> dict[str, Any]:
    if not video_media.variants:
        raise ValueError("YouTube video 媒体缺少 variants，无法按 quality 选取。")
    try:
        variant, _reason = pick_variant_by_quality(video_media.variants)
    except ValueError as exc:
        raise ValueError(f"YouTube 视频变体选取失败：{exc}") from exc
    return variant


def _resolve_separate_audio(
    *,
    post: SnapAnyPost,
    video_variant: dict[str, Any],
) -> tuple[str, str, int | None] | None:
    """独立音频：优先 Original；无则回退。无独立轨则返回 None（合成流）。"""
    audio_media = post.media_by_type("audio")
    if audio_media is not None and audio_media.variants:
        try:
            picked, _reason = pick_audio_variant(audio_media.variants)
        except ValueError:
            picked = None
        if picked is not None:
            return _audio_fields_from_variant(picked)

    return _audio_fields_from_variant(video_variant)


def _audio_fields_from_variant(
    variant: dict[str, Any],
) -> tuple[str, str, int | None] | None:
    audio_url = variant.get("audio_url")
    if not isinstance(audio_url, str) or not audio_url.strip():
        return None
    audio_url = audio_url.strip()
    audio_ext = variant.get("audio_ext")
    if not isinstance(audio_ext, str) or not audio_ext.strip():
        audio_ext = extension_from_url(audio_url, default="m4a")
    else:
        audio_ext = audio_ext.strip()
    filesize_raw = variant.get("audio_filesize")
    expected = int(filesize_raw) if filesize_raw is not None else None
    return audio_url, audio_ext, expected


def _resolve_srt_url(
    *,
    post: SnapAnyPost,
    video_media: Media,
    variant: dict[str, Any],
) -> str | None:
    target_lang = _resolve_target_language_tag(post, variant)
    if not target_lang:
        return None
    if not video_media.subtitles:
        return None

    matched = _match_subtitle_entry(video_media.subtitles, target_lang)
    if matched is None:
        return None

    for item in matched.urls:
        if item.format == "srt" and item.url and item.url.strip():
            return item.url.strip()
    return None


def _resolve_target_language_tag(post: SnapAnyPost, variant: dict[str, Any]) -> str | None:
    tag = variant.get("language_tag")
    if isinstance(tag, str) and tag.strip():
        return tag.strip()

    audio_media = post.media_by_type("audio")
    if audio_media is None:
        return None
    for item in audio_media.variants:
        if item.is_default is True and item.language_tag and item.language_tag.strip():
            return item.language_tag.strip()
    return None


def _match_subtitle_entry(subtitles: list[Subtitle], target_lang: str) -> Subtitle | None:
    target_norm = target_lang.strip().lower()
    target_primary = _primary_lang(target_norm)

    for item in subtitles:
        tag = item.language_tag
        if isinstance(tag, str) and tag.strip().lower() == target_norm:
            return item

    for item in subtitles:
        tag = item.language_tag
        if isinstance(tag, str) and _primary_lang(tag) == target_primary:
            return item
    return None


def _primary_lang(tag: str) -> str:
    text = tag.strip().lower().replace("_", "-")
    return text.split("-", 1)[0]
