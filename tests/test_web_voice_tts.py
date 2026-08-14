import asyncio

import pytest

from app.voice_chat.web_tts import (
    WebVoiceReplyBusyError,
    WebVoiceReplyNotFoundError,
    WebVoiceReplyRateLimitError,
    WebVoiceReplyStore,
)


def test_web_voice_reply_store_binds_reply_to_the_issuing_session() -> None:
    clock = [100.0]
    store = WebVoiceReplyStore(reply_ttl_seconds=60, min_interval_seconds=5, clock=lambda: clock[0])

    reply_id = asyncio.run(store.remember(user_id="profile-a", session_id="session-a", text="今晚风很轻。"))

    with pytest.raises(WebVoiceReplyNotFoundError):
        asyncio.run(store.acquire(reply_id, user_id="profile-b", session_id="session-a"))
    with pytest.raises(WebVoiceReplyNotFoundError):
        asyncio.run(store.acquire(reply_id, user_id="profile-a", session_id="session-b"))

    reply = asyncio.run(store.acquire(reply_id, user_id="profile-a", session_id="session-a"))

    assert reply.text == "今晚风很轻。"
    asyncio.run(store.release(reply_id))


def test_web_voice_reply_store_enforces_concurrency_rate_and_expiry() -> None:
    clock = [100.0]
    store = WebVoiceReplyStore(reply_ttl_seconds=10, min_interval_seconds=5, clock=lambda: clock[0])
    first_reply_id = asyncio.run(store.remember(user_id="profile-a", session_id="session-a", text="第一句。"))
    second_reply_id = asyncio.run(store.remember(user_id="profile-a", session_id="session-a", text="第二句。"))

    asyncio.run(store.acquire(first_reply_id, user_id="profile-a", session_id="session-a"))
    with pytest.raises(WebVoiceReplyBusyError):
        asyncio.run(store.acquire(second_reply_id, user_id="profile-a", session_id="session-a"))
    asyncio.run(store.release(first_reply_id))
    with pytest.raises(WebVoiceReplyRateLimitError):
        asyncio.run(store.acquire(second_reply_id, user_id="profile-a", session_id="session-a"))

    clock[0] += 11
    with pytest.raises(WebVoiceReplyNotFoundError):
        asyncio.run(store.acquire(first_reply_id, user_id="profile-a", session_id="session-a"))
