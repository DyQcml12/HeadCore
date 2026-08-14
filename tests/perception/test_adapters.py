from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.perception.adapters import AsrObservationAdapter
from app.providers.contracts import ProviderError, ProviderErrorCode


class StringAsr:
    provider = "fake-asr"
    model = "string-v1"

    def transcribe_file(self, path: Path) -> str:
        return "你好"


@dataclass
class ObjectAsrResult:
    text: str
    confidence: float
    emotion: str
    language: str


class ObjectAsr:
    provider = "fake-asr"
    model = "object-v1"

    def transcribe_file(self, path: Path) -> ObjectAsrResult:
        return ObjectAsrResult("测试语音", 0.91, "happy", "zh")


class MissingAsr:
    provider = "missing-asr"
    model = "missing"

    def transcribe_file(self, path: Path) -> str:
        raise ProviderError(ProviderErrorCode.MODEL_MISSING)


def test_asr_adapter_accepts_string_and_object_returns(tmp_path: Path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFFfake")

    string_result = AsrObservationAdapter(StringAsr()).observe(audio)
    object_result = AsrObservationAdapter(ObjectAsr()).observe(audio)

    assert string_result.output is not None
    assert string_result.output.text == "你好"
    assert object_result.output is not None
    assert object_result.output.text == "测试语音"
    assert object_result.output.confidence == 0.91
    assert object_result.output.emotion == "happy"


def test_asr_adapter_reports_model_missing_without_fake_text(tmp_path: Path) -> None:
    result = AsrObservationAdapter(MissingAsr()).observe(tmp_path / "missing.wav")

    assert result.output is None
    assert result.trace.success is False
    assert result.trace.error_code == "model_missing"
