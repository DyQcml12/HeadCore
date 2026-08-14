from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.audio.funasr_engine import AsrTranscriptionResult, FunAsrUnavailableError
from app.audio.enrichment import EmotionEnrichedAsrEngine
from app.providers import AsrRequest, ProviderError, ProviderErrorCode, ProviderId
from app.providers.funasr import FunAsrProvider


class FakeEngine:
    def __init__(self, result: object = "你好", error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    def transcribe_file(self, path: Path) -> object:
        if self.error:
            raise self.error
        return self.result


def test_funasr_provider_preserves_typed_result(tmp_path: Path) -> None:
    provider = FunAsrProvider(
        ProviderId("funasr"),
        FakeEngine(AsrTranscriptionResult("今天天气不错", emotion="happy")),
    )

    result = asyncio.run(provider.transcribe(AsrRequest(tmp_path / "sample.wav")))

    assert result.text == "今天天气不错"
    assert result.emotion == "happy"
    assert result.language == "zh"


class FakeEmotionEngine:
    def __init__(self, emotion: str | None) -> None:
        self.emotion = emotion

    def analyze_file(self, _path: Path):  # type: ignore[no-untyped-def]
        from app.audio.emotion_engine import AudioEmotionResult

        return AudioEmotionResult(
            emotion=self.emotion,
            emotion_source="emotion2vec",
            emotion_confidence=0.91 if self.emotion else None,
        )


def test_qq_asr_emotion_enrichment_overrides_sensevoice_when_available(
    tmp_path: Path,
) -> None:
    engine = EmotionEnrichedAsrEngine(
        FakeEngine(AsrTranscriptionResult("我今天很难受", emotion="neutral")),  # type: ignore[arg-type]
        FakeEmotionEngine("sad"),  # type: ignore[arg-type]
    )

    result = engine.transcribe_file(tmp_path / "voice.wav")

    assert result.emotion == "sad"
    assert result.emotion_source == "emotion2vec"
    assert result.emotion_confidence == 0.91


def test_qq_asr_emotion_enrichment_preserves_sensevoice_on_failure(
    tmp_path: Path,
) -> None:
    engine = EmotionEnrichedAsrEngine(
        FakeEngine(AsrTranscriptionResult("正常聊天", emotion="neutral")),  # type: ignore[arg-type]
        FakeEmotionEngine(None),  # type: ignore[arg-type]
    )

    result = engine.transcribe_file(tmp_path / "voice.wav")

    assert result.emotion == "neutral"
    assert result.emotion_source is None


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (FunAsrUnavailableError("missing"), ProviderErrorCode.MODEL_MISSING),
        (TimeoutError("slow"), ProviderErrorCode.TIMEOUT),
        (RuntimeError("offline"), ProviderErrorCode.UNAVAILABLE),
    ],
)
def test_funasr_provider_maps_failures(tmp_path: Path, error: Exception, code: ProviderErrorCode) -> None:
    provider = FunAsrProvider(ProviderId("funasr"), FakeEngine(error=error))

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.transcribe(AsrRequest(tmp_path / "sample.wav")))

    assert caught.value.code is code


def test_funasr_provider_rejects_empty_result(tmp_path: Path) -> None:
    provider = FunAsrProvider(ProviderId("funasr"), FakeEngine(""))

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.transcribe(AsrRequest(tmp_path / "sample.wav")))

    assert caught.value.code is ProviderErrorCode.INVALID_RESPONSE
