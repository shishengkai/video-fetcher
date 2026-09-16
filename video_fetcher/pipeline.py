from __future__ import annotations

from pathlib import Path

from video_fetcher.config import Settings, load_settings
from video_fetcher.models import SnapAnyPost, parse_snapany_post
from video_fetcher.parse_input import extract_single_url
from video_fetcher.sites import get_handler
from video_fetcher.snapany import extract_post


def run(input_text: str, settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    url = extract_single_url(input_text)
    raw = extract_post(url, settings.snapany_api_key)
    post: SnapAnyPost = parse_snapany_post(raw)

    handler = get_handler(post.site)
    out_dir = handler(post, settings)
    return str(out_dir.resolve())
