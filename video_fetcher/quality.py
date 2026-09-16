from __future__ import annotations

from typing import Any
from urllib.parse import unquote

# 视频轨：优先下载不超过该值的最高档；若全高于该值，则取其中最低档。
PREFERRED_MAX_QUALITY = 1080

_ORIGINAL_LABELS = frozenset({"original", "origianl"})  # 含常见拼写


def parse_quality(item: dict[str, Any]) -> int | None:
    raw = item.get("quality")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def is_original_label(item: dict[str, Any]) -> bool:
    label = item.get("quality_label")
    return isinstance(label, str) and label.strip().lower() in _ORIGINAL_LABELS


def is_original_audio(item: dict[str, Any]) -> bool:
    """Original 音轨：quality_label，或直链 xtags 中 acont=original。"""
    if is_original_label(item):
        return True
    for key in ("audio_url", "resource_url", "url"):
        raw = item.get(key)
        if isinstance(raw, str) and _url_marks_original_audio(raw):
            return True
    return False


def _url_marks_original_audio(url: str) -> bool:
    text = unquote(url).lower()
    return "acont=original" in text


def pick_variant_by_quality(variants: list[Any]) -> tuple[dict[str, Any], str]:
    """视频品质规则：≤1080 取最大；否则取 >1080 中最小。

    仅用于视频轨选取，不用于独立音频。
    返回 (variant, pick_reason)。无可用 quality 数值时抛出 ValueError。
    """
    dict_variants = [v for v in variants if isinstance(v, dict)]
    if not dict_variants:
        raise ValueError("variants 中没有任何对象项")

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in dict_variants:
        quality = parse_quality(item)
        if quality is not None:
            scored.append((quality, item))

    if not scored:
        raise ValueError(
            "variants 均缺少可用 quality 数值；"
            f"摘要={_variants_quality_summary(dict_variants)!r}"
        )

    at_or_below = [(q, v) for q, v in scored if q <= PREFERRED_MAX_QUALITY]
    if at_or_below:
        quality, best = max(at_or_below, key=lambda pair: pair[0])
        label = best.get("quality_label")
        reason = (
            f"quality={quality!r}（视频 ≤{PREFERRED_MAX_QUALITY} 中最大），"
            f"quality_label={label!r}"
        )
        return best, reason

    quality, best = min(scored, key=lambda pair: pair[0])
    label = best.get("quality_label")
    reason = (
        f"quality={quality!r}（视频无 ≤{PREFERRED_MAX_QUALITY}，"
        f"取 >{PREFERRED_MAX_QUALITY} 中最小），"
        f"quality_label={label!r}"
    )
    return best, reason


def pick_audio_variant(variants: list[Any]) -> tuple[dict[str, Any], str]:
    """音频选取：优先 Original，否则回退。

    优先级：
    1. quality_label=Original，或直链标记 acont=original
    2. is_default=true 且有 audio_url
    3. 第一条带 audio_url 的变体
    """
    dict_variants = [v for v in variants if isinstance(v, dict)]
    if not dict_variants:
        raise ValueError("音频 variants 中没有任何对象项")

    with_url = [
        v
        for v in dict_variants
        if isinstance(v.get("audio_url"), str) and v["audio_url"].strip()
    ]
    if not with_url:
        raise ValueError("音频 variants 均缺少 audio_url")

    for item in with_url:
        if is_original_audio(item):
            label = item.get("quality_label")
            lang = item.get("language_tag")
            return (
                item,
                f"音频优先 Original：quality_label={label!r}, language_tag={lang!r}",
            )

    for item in with_url:
        if item.get("is_default") is True:
            lang = item.get("language_tag")
            return (
                item,
                f"无 Original，回退 is_default 音频：language_tag={lang!r}",
            )

    first = with_url[0]
    lang = first.get("language_tag")
    return (
        first,
        f"无 Original/is_default，回退首条有 audio_url：language_tag={lang!r}",
    )


def _variants_quality_summary(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "quality": v.get("quality"),
            "quality_label": v.get("quality_label"),
            "has_video_url": bool(v.get("video_url")),
            "has_audio_url": bool(v.get("audio_url")),
        }
        for v in variants
    ]
