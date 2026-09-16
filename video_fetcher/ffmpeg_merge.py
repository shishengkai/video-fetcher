"""ffmpeg helpers (YouTube 音视频合并等)。抖音 MVP 暂不使用。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def merge_av_copy(video: Path, audio: Path, output: Path) -> Path:
    """用 ffmpeg 流复制合并音视频；成功后可用同名覆盖策略由调用方处理。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，请先安装并确保在 PATH 中。")

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-c",
        "copy",
        str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg 合并失败：\n"
            f"cmd={' '.join(cmd)}\n"
            f"stdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )
    return output
