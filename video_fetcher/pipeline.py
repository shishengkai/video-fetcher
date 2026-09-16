from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from video_fetcher.config import Settings, load_settings
from video_fetcher.parse_input import extract_single_url
from video_fetcher.sites import get_handler
from video_fetcher.snapany import extract_post

Handler = Callable[[dict[str, Any], Settings], Path]


def run(input_text: str, settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    url = extract_single_url(input_text)
    post = extract_post(url, settings.snapany_api_key)

    site = post.get("site")
    if not isinstance(site, str) or not site.strip():
        raise ValueError(
            "SnapAny 返回缺少 site 字段，无法选择下载规则。"
            f"顶层键={list(post.keys())}"
        )

    handler = get_handler(site.strip())
    out_dir = handler(post, settings)
    return str(out_dir.resolve())
