from __future__ import annotations

from typing import Any

# 优先下载不超过该值的最高档；若全高于该值，则取其中最低档。
PREFERRED_MAX_QUALITY = 1080


def parse_quality(item: dict[str, Any]) -> int | None:
    raw = item.get("quality")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def pick_variant_by_quality(variants: list[Any]) -> tuple[dict[str, Any], str]:
    """按品质规则选变体：≤1080 取最大；否则取 >1080 中最小。

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
            f"quality={quality!r}（≤{PREFERRED_MAX_QUALITY} 中最大），"
            f"quality_label={label!r}"
        )
        return best, reason

    quality, best = min(scored, key=lambda pair: pair[0])
    label = best.get("quality_label")
    reason = (
        f"quality={quality!r}（无 ≤{PREFERRED_MAX_QUALITY}，"
        f"取 >{PREFERRED_MAX_QUALITY} 中最小），"
        f"quality_label={label!r}"
    )
    return best, reason


def _variants_quality_summary(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "quality": v.get("quality"),
            "quality_label": v.get("quality_label"),
            "has_video_url": bool(v.get("video_url")),
        }
        for v in variants
    ]
