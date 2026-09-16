from __future__ import annotations

from pathlib import Path
from typing import Any

from video_fetcher.config import Settings


def download_post(post: dict[str, Any], settings: Settings) -> Path:
    raise NotImplementedError(
        "youtube 下载规则尚未实现。请先完成抖音链路验证，再按 Drafts 中的 YouTube 规则补齐。"
    )
