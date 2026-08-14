from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChannelPlatform(StrEnum):
    QQ = "qq"
    WEIXIN = "weixin"
    CORE_API = "core_api"


class ChannelEventType(StrEnum):
    MESSAGE = "message"
    RECALL = "recall"


class ChannelThreadType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"


class AttachmentKind(StrEnum):
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    STICKER = "sticker"
    FORWARD = "forward"
    CARD = "card"
    LOCATION = "location"
    UNKNOWN = "unknown"


class ResponsePartKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO_ATTACHMENT = "audio_attachment"
    NATIVE_VOICE = "native_voice"
    TYPING = "typing"
    RECALL = "recall"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)


class ChannelIdentity(ContractModel):
    platform: ChannelPlatform
    user_id: str = Field(min_length=1, max_length=256)
    display_name: str | None = Field(default=None, max_length=256)

    @field_validator("user_id", mode="before")
    @classmethod
    def preserve_user_id(cls, value: Any) -> str:
        value = str(value).strip() if value is not None else ""
        if not value:
            raise ValueError("user_id must not be empty")
        return value


class ChannelThread(ContractModel):
    platform: ChannelPlatform
    thread_type: ChannelThreadType
    thread_id: str = Field(min_length=1, max_length=256)
    group_id: str | None = Field(default=None, max_length=256)

    @field_validator("thread_id", mode="before")
    @classmethod
    def preserve_thread_id(cls, value: Any) -> str:
        value = str(value).strip() if value is not None else ""
        if not value:
            raise ValueError("thread_id must not be empty")
        return value

    @field_validator("group_id", mode="before")
    @classmethod
    def preserve_group_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip() or None


class ChannelAttachment(ContractModel):
    kind: AttachmentKind
    media_type: str | None = Field(default=None, max_length=128)
    display_name: str | None = Field(default=None, max_length=256)
    size_bytes: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    source_ref: str | None = Field(default=None, max_length=256)
    summary: str = Field(min_length=1, max_length=500)
    original_type: str | None = Field(default=None, max_length=64)


class ChannelMessage(ContractModel):
    message_id: str = Field(min_length=1, max_length=256)
    timestamp: datetime
    text: str = Field(default="", max_length=10000)
    attachments: tuple[ChannelAttachment, ...] = ()
    reply_to_message_id: str | None = Field(default=None, max_length=256)

    @field_validator("message_id", "reply_to_message_id", mode="before")
    @classmethod
    def preserve_message_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip() or None

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)


class ChannelEvent(ContractModel):
    event_type: ChannelEventType
    platform: ChannelPlatform
    identity: ChannelIdentity
    thread: ChannelThread
    occurred_at: datetime
    message: ChannelMessage | None = None
    recalled_message_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, str | bool | int | float | None] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_payload(self) -> ChannelEvent:
        if self.event_type == ChannelEventType.MESSAGE and self.message is None:
            raise ValueError("message event must include message")
        if self.event_type == ChannelEventType.RECALL and not self.recalled_message_id:
            raise ValueError("recall event must include recalled_message_id")
        return self


class ChannelCapabilitySet(ContractModel):
    text: bool = True
    image: bool = False
    file: bool = False
    audio_attachment: bool = False
    native_voice: bool = False
    recall: bool = False
    typing: bool = False
    profile_update: bool = False
    voice_call: bool = False


class ChannelResponsePart(ContractModel):
    kind: ResponsePartKind
    content: str = Field(min_length=1, max_length=10000)
    media_type: str | None = Field(default=None, max_length=128)


class ChannelResponse(ContractModel):
    parts: tuple[ChannelResponsePart, ...]
    reply_to_message_id: str | None = Field(default=None, max_length=256)


class DeliveryResult(ContractModel):
    status: Literal["delivered", "degraded", "unsupported", "failed"]
    delivered_parts: tuple[ChannelResponsePart, ...] = ()
    omitted_parts: tuple[ChannelResponsePart, ...] = ()
    reason: str | None = Field(default=None, max_length=500)
