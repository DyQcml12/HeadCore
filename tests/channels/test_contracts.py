from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.channels.contracts import (
    ChannelEvent,
    ChannelEventType,
    ChannelIdentity,
    ChannelMessage,
    ChannelPlatform,
    ChannelThread,
    ChannelThreadType,
)


def test_contract_json_round_trip_is_stable() -> None:
    timestamp = datetime(2026, 7, 14, 4, 30, tzinfo=timezone.utc)
    event = ChannelEvent(
        event_type=ChannelEventType.MESSAGE,
        platform=ChannelPlatform.QQ,
        identity=ChannelIdentity(platform=ChannelPlatform.QQ, user_id=90071992547409931234),
        thread=ChannelThread(
            platform=ChannelPlatform.QQ,
            thread_type=ChannelThreadType.PRIVATE,
            thread_id=90071992547409931234,
        ),
        occurred_at=timestamp,
        message=ChannelMessage(message_id=12345678901234567890, timestamp=timestamp, text="你好"),
    )

    restored = ChannelEvent.model_validate_json(event.model_dump_json())

    assert restored == event
    assert restored.identity.user_id == "90071992547409931234"
    assert restored.message is not None
    assert restored.message.message_id == "12345678901234567890"


def test_message_timestamp_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        ChannelMessage(message_id="1", timestamp=datetime(2026, 7, 14), text="hello")


def test_event_payload_must_match_event_type() -> None:
    timestamp = datetime.now(timezone.utc)
    common = {
        "platform": ChannelPlatform.QQ,
        "identity": ChannelIdentity(platform=ChannelPlatform.QQ, user_id="1"),
        "thread": ChannelThread(
            platform=ChannelPlatform.QQ,
            thread_type=ChannelThreadType.PRIVATE,
            thread_id="1",
        ),
        "occurred_at": timestamp,
    }
    with pytest.raises(ValidationError, match="must include message"):
        ChannelEvent(event_type=ChannelEventType.MESSAGE, **common)
    with pytest.raises(ValidationError, match="recalled_message_id"):
        ChannelEvent(event_type=ChannelEventType.RECALL, **common)

