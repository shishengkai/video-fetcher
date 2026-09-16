from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from video_fetcher.config import Settings


def post_dir(settings: Settings, site: str, post_id: str) -> Path:
    if not site:
        raise ValueError("缺少 site：无法构造保存目录。")
    if not post_id:
        raise ValueError("缺少 id：无法构造保存目录。")
    path = settings.download_dir / f"{site}-{post_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def extension_from_url(url: str, default: str = "bin") -> str:
    path = unquote(urlparse(url).path)
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        # 去掉怪异超长“扩展名”
        if 1 <= len(ext) <= 8 and ext.isalnum():
            return ext
    return default
