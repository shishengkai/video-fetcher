from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "manifest.json"

# 约定字段顺序，便于人类与下游程序阅读；无值的键不会写出。
_FIELD_ORDER = (
    "site",
    "id",
    "title",
    "text",
    "created_at",
    "duration",
    "post_url",
    "preview_file",
    "video_file",
    "subtitles_file",
)


def build_manifest(**fields: Any) -> dict[str, Any]:
    """组装 manifest；None / 空字符串的键省略。"""
    data: dict[str, Any] = {}
    for key in _FIELD_ORDER:
        if key not in fields:
            continue
        value = fields[key]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        data[key] = value.strip() if isinstance(value, str) else value
    # 允许未来扩展字段（仍跳过空值）
    for key, value in fields.items():
        if key in data or key in _FIELD_ORDER:
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        data[key] = value.strip() if isinstance(value, str) else value
    return data


def write_manifest(directory: Path, data: dict[str, Any]) -> Path:
    path = directory / MANIFEST_FILENAME
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
