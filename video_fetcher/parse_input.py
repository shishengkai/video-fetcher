from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>'\"，。；：！？、）》」』】"


def extract_single_url(text: str) -> str:
    """从输入中提取恰好一个 URL；否则抛出带说明的 ValueError。"""
    if not text or not text.strip():
        raise ValueError("输入为空：请提供 URL 或分享字符串。")

    found: list[str] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(_TRAILING_PUNCT)
        if url:
            found.append(url)

    if len(found) == 0:
        raise ValueError("输入有误：未找到 URL。请提供纯 URL，或包含一个 URL 的分享字符串。")
    if len(found) > 1:
        listed = "\n".join(f"  - {u}" for u in found)
        raise ValueError(f"输入有误：找到 {len(found)} 个 URL，需要恰好 1 个：\n{listed}")
    return found[0]
