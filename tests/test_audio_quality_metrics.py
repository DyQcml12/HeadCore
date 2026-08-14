from __future__ import annotations

import pytest
from pathlib import Path
import json

from app.audio.quality_metrics import character_error_rate, normalize_transcript
from app.audio.funasr_engine import AsrTranscriptionResult
from scripts.asr_batch_stress import evaluate_result, load_samples, run_batch


def test_transcript_normalization_ignores_case_spacing_and_punctuation() -> None:
    assert normalize_transcript("Hello，世界！") == "hello世界"


def test_character_error_rate_counts_substitution_deletion_and_insertion() -> None:
    assert character_error_rate("欢迎体验", "欢迎体验") == 0
    assert character_error_rate("欢迎体验", "欢迎体检") == pytest.approx(0.25)
    assert character_error_rate("欢迎体验", "欢迎体") == pytest.approx(0.25)


def test_batch_evaluator_rejects_transcript_over_cer_threshold() -> None:
    passed, reasons, cer = evaluate_result(
        {"expected_text": "欢迎大家来体验", "max_cer": 0.1},
        "天气不错",
        None,
    )

    assert passed is False
    assert cer is not None and cer > 0.1
    assert any("字符错误率超标" in reason for reason in reasons)


def test_stress_samples_inherit_reference_transcript() -> None:
    if not Path("data/asr_samples/stress_manifest.json").exists():
        pytest.skip("local ASR stress samples are not present")
    samples = load_samples(
        [
            Path("data/asr_samples/manifest.json"),
            Path("data/asr_samples/stress_manifest.json"),
        ]
    )
    derived = next(
        sample
        for sample in samples
        if sample.get("source_sample_id") == "funasr-zh-example-001"
    )

    assert derived["expected_text"].startswith("欢迎大家")
    assert 0 < float(derived["max_cer"]) <= 0.5


def test_batch_stress_accepts_structured_funasr_transcription_result(tmp_path: Path) -> None:
    class StructuredEngine:
        model = "structured-test-model"

        def transcribe_file(self, audio_path: Path) -> AsrTranscriptionResult:
            assert audio_path.exists()
            return AsrTranscriptionResult(text="欢迎大家来体验语音识别模型。", emotion="happy")

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "id": "structured-result",
                    "path": str(audio_path),
                    "expected_text": "欢迎大家来体验语音识别模型。",
                    "max_cer": 0.1,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = run_batch(
        manifest_paths=[manifest_path],
        output_root=tmp_path / "reports",
        engine=StructuredEngine(),
    )
    assert report.exists()
    result = json.loads((report.parent / "asr-batch-stress-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["results"][0]["text"] == "欢迎大家来体验语音识别模型。"
