from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.channels.adapters import CoreApiEventAdapter
from app.channels.contracts import (
    ChannelEvent,
    ChannelEventType,
    ChannelIdentity,
    ChannelPlatform,
    ChannelThread,
    ChannelThreadType,
)
from app.head.runtime import HeadRuntime, HeadRuntimeContext, UnsupportedHeadEventError
from app.schemas import ChatRequest, ChatResponse


class RecordingChatService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def reply(self, user_input: str, **kwargs: object) -> ChatResponse:
        self.calls.append((user_input, kwargs))
        return ChatResponse(
            text="胡桃收到。",
            provider="fake",
            model="fake",
            used_live_api=False,
        )

    async def stream_reply(self, user_input: str, **kwargs: object):
        self.calls.append((user_input, kwargs))
        yield "胡桃"
        yield "收到。"


def test_head_runtime_maps_channel_event_to_cognitive_entry() -> None:
    service = RecordingChatService()
    runtime = HeadRuntime(service)
    event = CoreApiEventAdapter().adapt(
        ChatRequest(
            user_input="继续开发人头",
            session_id="session-1",
            user_id="internal-user",
            platform="qq",
            platform_user_id="10001",
            platform_group_id="20002",
            input_source="audio",
        )
    )
    context = HeadRuntimeContext(
        subject_id="profile-1",
        session_id="session-1",
        input_source="audio",
        input_quality_reasons=("low_confidence",),
    )

    response = asyncio.run(runtime.handle(event, context))

    assert response.text == "胡桃收到。"
    text, kwargs = service.calls[0]
    assert text == "继续开发人头"
    assert kwargs["user_id"] == "profile-1"
    assert kwargs["platform"] == "qq"
    assert kwargs["platform_user_id"] == "10001"
    assert kwargs["platform_group_id"] == "20002"
    assert kwargs["input_source"] == "audio"
    assert kwargs["head_runtime_origin"] == "channel_event"


def test_head_runtime_stream_uses_the_same_entry_mapping() -> None:
    service = RecordingChatService()
    runtime = HeadRuntime(service)
    event = CoreApiEventAdapter().adapt(
        ChatRequest(user_input="继续", session_id="s1", user_id="u1")
    )

    async def collect() -> str:
        chunks = [chunk async for chunk in runtime.stream(
            event,
            HeadRuntimeContext(subject_id="u1", session_id="s1"),
        )]
        return "".join(chunks)

    assert asyncio.run(collect()) == "胡桃收到。"
    assert service.calls[0][1]["head_runtime_origin"] == "channel_event"


def test_head_runtime_rejects_non_message_events() -> None:
    now = datetime.now(timezone.utc)
    event = ChannelEvent(
        event_type=ChannelEventType.RECALL,
        platform=ChannelPlatform.CORE_API,
        identity=ChannelIdentity(platform=ChannelPlatform.CORE_API, user_id="u1"),
        thread=ChannelThread(
            platform=ChannelPlatform.CORE_API,
            thread_type=ChannelThreadType.PRIVATE,
            thread_id="s1",
        ),
        occurred_at=now,
        recalled_message_id="m1",
    )

    with pytest.raises(UnsupportedHeadEventError):
        asyncio.run(
            HeadRuntime(RecordingChatService()).handle(
                event,
                HeadRuntimeContext(subject_id="u1", session_id="s1"),
            )
        )
