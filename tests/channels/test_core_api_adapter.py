from __future__ import annotations

from datetime import datetime, timezone

from app.channels.adapters import CoreApiEventAdapter
from app.schemas import ChatRequest


def test_core_api_request_uses_platform_identity_when_present() -> None:
    timestamp = datetime(2026, 7, 14, 5, 0, tzinfo=timezone.utc)
    request = ChatRequest(
        user_input="你好",
        session_id="session-1",
        user_id="internal-user",
        platform="qq",
        platform_user_id="qq-user",
        platform_group_id="qq-group",
    )

    event = CoreApiEventAdapter().adapt(request, occurred_at=timestamp)

    assert event.platform == "core_api"
    assert event.identity.user_id == "qq-user"
    assert event.thread.thread_type == "group"
    assert event.thread.thread_id == "qq-group"
    assert event.metadata["source_platform"] == "qq"
    assert event.message is not None
    assert event.message.text == "你好"
    assert event.message.message_id.startswith("core-api-")


def test_core_api_request_falls_back_to_internal_user_and_session() -> None:
    event = CoreApiEventAdapter().adapt(
        {"user_input": "hello", "session_id": "s-1", "user_id": 123},
        occurred_at=datetime.now(timezone.utc),
    )

    assert event.identity.user_id == "123"
    assert event.thread.thread_id == "s-1"
    assert event.thread.thread_type == "private"

