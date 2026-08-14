from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.audio.funasr_engine import AsrTranscriptionResult, FunAsrUnavailableError
from app.providers import AsrRequest, ProviderCapability, ProviderError, ProviderErrorCode, ProviderId
from app.providers import ProviderRegistry, ProviderRouter, RoutingFailed, RoutingPolicy
from app.providers.funasr import FunAsrProvider


class FakeEngine:
    provider = "funasr"
    model = "fake-model"

    def __init__(self, outcome, *, delay: float = 0.0) -> None:
        self.outcome = outcome
        self.delay = delay

    def transcribe_file(self, path: Path):
        if self.delay:
            time.sleep(self.delay)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_funasr_provider_preserves_emotion_metadata(tmp_path: Path) -> None:
    provider = FunAsrProvider(
        ProviderId("funasr-test"),
        FakeEngine(AsrTranscriptionResult("你好", "happy", "sensevoice_tag", 0.8)),
    )

    result = asyncio.run(provider.transcribe(AsrRequest(tmp_path / "sample.wav")))

    assert result.text == "你好"
    assert result.emotion == "happy"
    assert result.emotion_source == "sensevoice_tag"
    assert result.emotion_confidence == 0.8


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (FunAsrUnavailableError("not installed"), ProviderErrorCode.MODEL_MISSING),
        (RuntimeError("model checkpoint missing"), ProviderErrorCode.MODEL_MISSING),
        (AsrTranscriptionResult(""), ProviderErrorCode.INVALID_RESPONSE),
    ],
)
def test_funasr_provider_maps_failures(tmp_path: Path, outcome: object, code: ProviderErrorCode) -> None:
    provider = FunAsrProvider(ProviderId("funasr-test"), FakeEngine(outcome))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.transcribe(AsrRequest(tmp_path / "sample.wav")))
    assert caught.value.code is code


def test_funasr_router_enforces_timeout(tmp_path: Path) -> None:
    provider = FunAsrProvider(
        ProviderId("funasr-slow"),
        FakeEngine(AsrTranscriptionResult("迟到"), delay=0.05),
    )
    registry = ProviderRegistry()
    registry.register(provider)

    with pytest.raises(RoutingFailed) as caught:
        asyncio.run(
            ProviderRouter(registry).route(
                ProviderCapability.ASR,
                RoutingPolicy((provider.provider_id,), timeout_seconds=0.01),
                lambda item: item.transcribe(AsrRequest(tmp_path / "sample.wav")),
            )
        )

    assert caught.value.trace.attempts[0].error_code is ProviderErrorCode.TIMEOUT
