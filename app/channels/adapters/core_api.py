from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.channels.contracts import (
    ChannelEvent,
    ChannelEventType,
    ChannelIdentity,
    ChannelMessage,
    ChannelPlatform,
    ChannelThread,
    ChannelThreadType,
)


class CoreApiEventAdapter:
    def adapt(self, request: object, *, occurred_at: datetime | None = None) -> ChannelEvent:
        user_id = _required(request, "platform_user_id", fallback_key="user_id")
        group_id = _optional(request, "platform_group_id")
        session_id = _required(request, "session_id")
        timestamp = (occurred_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        thread_type = ChannelThreadType.GROUP if group_id else ChannelThreadType.PRIVATE
        thread_id = group_id or session_id
        identity = ChannelIdentity(platform=ChannelPlatform.CORE_API, user_id=user_id)
        thread = ChannelThread(
            platform=ChannelPlatform.CORE_API,
            thread_type=thread_type,
            thread_id=thread_id,
            group_id=group_id,
        )
        message = ChannelMessage(
            message_id=_optional(request, "message_id") or f"core-api-{uuid4().hex}",
            timestamp=timestamp,
            text=_required(request, "user_input"),
        )
        return ChannelEvent(
            event_type=ChannelEventType.MESSAGE,
            platform=ChannelPlatform.CORE_API,
            identity=identity,
            thread=thread,
            occurred_at=timestamp,
            message=message,
            metadata={"source_platform": _optional(request, "platform")},
        )


def _value(request: object, key: str) -> Any:
    if isinstance(request, Mapping):
        return request.get(key)
    return getattr(request, key, None)


def _optional(request: object, key: str) -> str | None:
    value = _value(request, key)
    return str(value).strip() or None if value is not None else None


def _required(request: object, key: str, *, fallback_key: str | None = None) -> str:
    value = _optional(request, key)
    if value is None and fallback_key:
        value = _optional(request, fallback_key)
    if value is None:
        raise ValueError(f"Core API request is missing {key}")
    return value

