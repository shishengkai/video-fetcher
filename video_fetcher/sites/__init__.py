from __future__ import annotations

from typing import Any, Callable
from pathlib import Path

from video_fetcher.config import Settings
from video_fetcher.sites import douyin, weixin, youtube

Handler = Callable[[dict[str, Any], Settings], Path]

_HANDLERS: dict[str, Handler] = {
    "douyin": douyin.download_post,
    "youtube": youtube.download_post,
    "weixin": weixin.download_post,
}


def get_handler(site: str) -> Handler:
    handler = _HANDLERS.get(site)
    if handler is None:
        supported = ", ".join(sorted(_HANDLERS))
        raise ValueError(
            f"暂不支持的 site={site!r}。当前已注册：{supported}。"
        )
    return handler
