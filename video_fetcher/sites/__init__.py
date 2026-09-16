from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from video_fetcher.config import Settings
from video_fetcher.models import SnapAnyPost
from video_fetcher.sites import bilibili, douyin, generic, weixin, youtube

Handler = Callable[[SnapAnyPost, Settings], Path]

_HANDLERS: dict[str, Handler] = {
    "bilibili": bilibili.download_post,
    "douyin": douyin.download_post,
    "youtube": youtube.download_post,
    "weixin": weixin.download_post,
}


def get_handler(site: str) -> Handler:
    """返回站点专用下载器；无专用实现时回退通用下载器。"""
    return _HANDLERS.get(site, generic.download_post)


def specialized_sites() -> list[str]:
    return sorted(_HANDLERS)
