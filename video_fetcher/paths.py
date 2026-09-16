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


def id_from_post_url(post_url: str) -> str:
    """取 post_url 路径的最后一节作为 id（去掉末尾 /）。"""
    if not isinstance(post_url, str) or not post_url.strip():
        raise ValueError("post_url 为空，无法回退解析 id。")
    path = unquote(urlparse(post_url.strip()).path).rstrip("/")
    if not path:
        raise ValueError(f"无法从 post_url 解析 id（无路径）: {post_url!r}")
    segment = path.rsplit("/", 1)[-1].strip()
    if not segment:
        raise ValueError(f"无法从 post_url 解析 id（最后一节为空）: {post_url!r}")
    return segment


def extension_from_url(url: str, default: str = "bin") -> str:
    path = unquote(urlparse(url).path)
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        # 去掉怪异超长“扩展名”
        if 1 <= len(ext) <= 8 and ext.isalnum():
            return ext
    return default
