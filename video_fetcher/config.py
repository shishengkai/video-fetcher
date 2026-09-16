from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    snapany_api_key: str
    download_dir: Path


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    key = (os.getenv("SNAPANY_API_KEY") or "").strip()
    raw_dir = (os.getenv("DOWNLOAD_DIR") or "").strip()
    if not key:
        raise ValueError("缺少 SNAPANY_API_KEY：请在 .env 中填写 SnapAny API Key。")
    if not raw_dir:
        raise ValueError("缺少 DOWNLOAD_DIR：请在 .env 中填写下载主目录。")

    download_dir = Path(os.path.expandvars(os.path.expanduser(raw_dir))).expanduser()
    try:
        download_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"无法创建或访问 DOWNLOAD_DIR={download_dir}: {exc}") from exc

    return Settings(snapany_api_key=key, download_dir=download_dir.resolve())
