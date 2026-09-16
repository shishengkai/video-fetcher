from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class Variant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quality: int | float | str | None = None
    quality_label: str | None = None
    fps: Any = None
    duration: Any = None
    video_url: str | None = None
    video_ext: str | None = None
    video_codec: str | None = None
    video_filesize: int | float | str | None = None
    audio_url: str | None = None
    audio_ext: str | None = None
    audio_codec: str | None = None
    audio_filesize: int | float | str | None = None
    language_tag: str | None = None
    language_name: str | None = None
    is_default: bool | None = None


class SubtitleUrl(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str | None = None
    format: str | None = None


class Subtitle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language_tag: str | None = None
    language_name: str | None = None
    urls: list[SubtitleUrl] = Field(default_factory=list)


class Media(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media_type: str | None = None
    resource_url: str | None = None
    preview_url: str | None = None
    duration: Any = None
    headers: dict[str, str] = Field(default_factory=dict)
    variants: list[Variant] = Field(default_factory=list)
    subtitles: list[Subtitle] = Field(default_factory=list)

    @field_validator("headers", mode="before")
    @classmethod
    def _coerce_headers(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        return {}


class SnapAnyPost(BaseModel):
    """SnapAny extract/post 最小契约；未知字段忽略。"""

    model_config = ConfigDict(extra="ignore")

    site: str
    post_url: str
    id: str | int | float | None = None
    title: str | None = None
    text: str | None = None
    created_at: Any = None
    duration: Any = None
    medias: list[Media] = Field(default_factory=list)

    @field_validator("site", "post_url", mode="before")
    @classmethod
    def _require_nonempty_str(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("必须是非空字符串")
        return value.strip()

    @field_validator("title", "text", mode="before")
    @classmethod
    def _optional_str(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return str(value)

    def api_id(self) -> str | None:
        """接口真 id；无则 None（目录名可另由 post_url 回退）。"""
        if self.id is None:
            return None
        text = str(self.id).strip()
        return text or None

    def require_api_id(self) -> str:
        value = self.api_id()
        if not value:
            raise ValueError("结果缺少有效 id 字段。")
        return value

    def media_by_type(self, media_type: str) -> Media | None:
        return next((m for m in self.medias if m.media_type == media_type), None)

    def require_video_media(self, *, site_label: str) -> Media:
        media = self.media_by_type("video")
        if media is not None:
            return media
        raise ValueError(f"{site_label}结果中未找到 media_type=video 的项。")

    def require_medias(self, *, site_label: str) -> list[Media]:
        if not self.medias:
            raise ValueError(f"{site_label}结果缺少 medias 数组。")
        return self.medias

    def manifest_created_at(self) -> str | int | float | None:
        value = self.created_at
        if value is None:
            return None
        if isinstance(value, (str, int, float)):
            return value
        return str(value)


def parse_snapany_post(data: Any) -> SnapAnyPost:
    """将 SnapAny JSON 解析为模型；失败时抛出可读 ValidationError 摘要。"""
    try:
        return SnapAnyPost.model_validate(data)
    except ValidationError as exc:
        top_keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
        raise ValueError(
            "SnapAny 返回不符合最小契约，无法继续下载。\n"
            f"顶层键={top_keys}\n"
            f"{exc}"
        ) from exc


def first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None
