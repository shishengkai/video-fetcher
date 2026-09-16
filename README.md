# video-fetcher（猎影者）

用 Python 调用 SnapAny，从视频 URL 或分享串下载到本地，并**打印保存目录路径**。

中文名：**猎影者**；工程 / CLI / 包名仍为 `video-fetcher`。

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

依赖要点：`requests` Session 处理连接重试；`tenacity` 处理提取/下载业务重试；`pydantic` 校验 SnapAny 最小响应契约。

## 当前支持

| site | 状态 |
| --- | --- |
| `douyin` | 已实现（`manifest.json`；视频 ≤1080 最大 / 否则 >1080 最小；稀疏返回回退；同帖媒体并行下载） |
| `youtube` | 已实现（视频 ≤1080；音频优先 Original 再回退；同帖媒体并行下载；分离轨则 ffmpeg 合并；字幕语言回退） |
| `weixin` | 已实现（`resource_url` + 封面；目录 id 取自 `post_url`；同帖媒体并行下载） |
| `bilibili` | 已实现（仅 `resource_url`；BV id 取自 `post_url` 末节并写入 manifest；须带 headers；同帖并行） |

项目规范与设计见配套 brain：`video-fetcher-brain`。
