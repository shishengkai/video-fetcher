from __future__ import annotations

import argparse
import sys

from video_fetcher.pipeline import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="video-fetcher",
        description="从 URL 或分享串下载视频到本地，并打印保存目录路径。",
    )
    parser.add_argument(
        "input_text",
        nargs="?",
        help="纯 URL，或包含恰好一个 URL 的分享字符串；省略则从 stdin 读取",
    )
    args = parser.parse_args(argv)

    text = args.input_text
    if text is None:
        text = sys.stdin.read()
    text = (text or "").strip()
    if not text:
        print("输入为空：请提供 URL 或分享字符串。", file=sys.stderr)
        return 2

    try:
        out_dir = run(text)
    except Exception as exc:  # noqa: BLE001 — CLI 边界统一输出可读错误
        print(str(exc), file=sys.stderr)
        return 1

    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
