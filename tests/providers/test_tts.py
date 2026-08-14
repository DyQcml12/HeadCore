from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.providers import GptSoVitsTtsProvider, ProviderError, ProviderErrorCode, TtsRequest, normalize_tts_provider_id
from app.voice_chat.tts_service import VoiceSynthesisResult


def test_tts_provider_runs_existing_synthesizer_and_returns_send_path(tmp_path: Path) -> None:
    send_path = tmp_path / "reply.mp3"

    def synthesize(**kwargs) -> VoiceSynthesisResult:
        assert kwargs["provider"] == "gpt_sovits"
        assert kwargs["reply_text"] == "你好"
        return VoiceSynthesisResult(tmp_path / "reply.wav", send_path, "neutral", "你好")

    provider = GptSoVitsTtsProvider(synthesize, {"base_url": "http://127.0.0.1:9880"})
    result = asyncio.run(
        provider.synthesize(TtsRequest("你好", tmp_path / "pending.wav", user_input="说句话"))
    )

    assert result == send_path


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (RuntimeError("credentials are missing"), ProviderErrorCode.NOT_CONFIGURED),
        (RuntimeError("TTS HTTP 429"), ProviderErrorCode.RATE_LIMITED),
        (TimeoutError("timed out"), ProviderErrorCode.TIMEOUT),
        (RuntimeError("returned empty audio"), ProviderErrorCode.INVALID_RESPONSE),
    ],
)
def test_tts_provider_maps_existing_errors(tmp_path: Path, error: Exception, code: ProviderErrorCode) -> None:
    def synthesize(**kwargs):
        raise error

    provider = GptSoVitsTtsProvider(synthesize, {})
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.synthesize(TtsRequest("你好", tmp_path / "pending.wav")))
    assert caught.value.code is code


def test_tts_provider_aliases_are_canonical() -> None:
    assert normalize_tts_provider_id("GPT-SoVITS").value == "gpt_sovits"
    assert normalize_tts_provider_id("gptsovits").value == "gpt_sovits"


def test_gpt_sovits_provider_uses_canonical_id(tmp_path: Path) -> None:
    def synthesize(**kwargs) -> VoiceSynthesisResult:
        assert kwargs["provider"] == "gpt_sovits"
        return VoiceSynthesisResult(tmp_path / "reply.wav", tmp_path / "reply.mp3", "neutral", kwargs["reply_text"])

    result = asyncio.run(GptSoVitsTtsProvider(synthesize, {}).synthesize(TtsRequest("你好", tmp_path / "pending.wav")))
    assert result.name == "reply.mp3"
