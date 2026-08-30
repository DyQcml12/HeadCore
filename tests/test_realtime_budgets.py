from __future__ import annotations

import asyncio
from dataclasses import replace

import app.main as main_mod
from app.core.config import load_settings
from app.schemas import ChatResponse


class _SlowRuntime:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    async def handle(self, channel_event, context) -> ChatResponse:  # type: ignore[no-untyped-def]
        await asyncio.sleep(self.delay)
        return ChatResponse(text="ok", provider="fake", model="fake", used_live_api=False)


def test_api_timeout_seconds_is_clamped_to_router_bounds(monkeypatch) -> None:
    monkeypatch.setenv("API_TIMEOUT_SECONDS", "600")
    assert load_settings().request_timeout_seconds == 300.0

    monkeypatch.setenv("API_TIMEOUT_SECONDS", "0")
    assert load_settings().request_timeout_seconds == 1.0

    monkeypatch.setenv("API_TIMEOUT_SECONDS", "45")
    assert load_settings().request_timeout_seconds == 45.0


def test_public_web_tts_total_budget_seconds_default_and_override(monkeypatch) -> None:
    monkeypatch.delenv("PUBLIC_WEB_TTS_TOTAL_BUDGET_SECONDS", raising=False)
    assert load_settings().public_web_tts_total_budget_seconds == 120

    monkeypatch.setenv("PUBLIC_WEB_TTS_TOTAL_BUDGET_SECONDS", "45")
    assert load_settings().public_web_tts_total_budget_seconds == 45


def test_reply_with_audio_budget_returns_fallback_on_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        main_mod,
        "settings",
        replace(load_settings(), voice_chat_reply_timeout_seconds=0.05),
    )
    runtime = _SlowRuntime(delay=1.0)

    result = asyncio.run(main_mod._reply_with_audio_budget(runtime, None, None))

    assert result.model == "audio-chat-timeout"
    assert result.fallback_used is True
    assert "\u91cd\u8bd5" in result.text


def test_reply_with_audio_budget_returns_reply_before_deadline(monkeypatch) -> None:
    monkeypatch.setattr(
        main_mod,
        "settings",
        replace(load_settings(), voice_chat_reply_timeout_seconds=1.0),
    )
    runtime = _SlowRuntime(delay=0.01)

    result = asyncio.run(main_mod._reply_with_audio_budget(runtime, None, None))

    assert result.text == "ok"
