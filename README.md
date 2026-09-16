# video-fetcher

用 Python 调用 SnapAny，从视频 URL 或分享串下载到本地，并**打印保存目录路径**。

## 配置

```bash
cp .env.sample .env
# 编辑 .env：填入 SNAPANY_API_KEY 与 DOWNLOAD_DIR
```

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## 使用

```bash
video-fetcher '这里是分享文案 https://v.douyin.com/xxxx/'
# 或
python -m video_fetcher 'https://v.douyin.com/xxxx/'
```

成功时标准输出只有一行：下载目录的绝对路径。目录内含媒体文件与固定名 `manifest.json`（下游程序入口）。

## 当前支持

| site | 状态 |
| --- | --- |
| `douyin` | 已实现（`manifest.json`；稀疏返回回退齐全；同帖媒体并行下载） |
| `youtube` | 已实现（最高 quality；同帖媒体并行下载；分离轨则 ffmpeg 合并；字幕语言回退） |
| `weixin` | 已实现（`resource_url` + 封面；目录 id 取自 `post_url`；同帖媒体并行下载） |

项目规范与设计见配套 brain：`video-fetcher-brain`。
