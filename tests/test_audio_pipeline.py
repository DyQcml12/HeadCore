from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.audio.chat_input import clean_asr_text_for_chat
from app.audio.chat_input import prepare_audio_chat_input
from app.audio.emotion_engine import AudioEmotionResult
from app.audio.emotion_engine import normalize_emotion_label
from app.audio.emotion_engine import parse_emotion2vec_result
from app.audio.file_service import enrich_with_audio_emotion
from app.audio.file_service import parse_asr_file_presets
from app.audio.file_service import parse_optional_asr_presets
from app.audio.funasr_engine import AsrTranscriptionResult
from app.audio.funasr_engine import FunAsrFileEngine
from app.audio.funasr_engine import FunAsrUnavailableError
from app.audio.funasr_engine import clean_asr_text
from app.audio.funasr_engine import extract_text
from app.audio.funasr_engine import extract_transcription_result
from app.audio.model_paths import resolve_funasr_aux_model
from app.audio.model_paths import resolve_modelscope_model
from app.audio.pipeline import NamedFileAsrEngine
from app.audio.pipeline import transcribe_with_candidates
from app.audio.pipeline import transcribe_with_repair_candidates
from app.audio.quality import evaluate_asr_text_quality
from app.audio.schemas import AsrEvent
from app.audio.schemas import AsrFileResponse
from app.audio.stream_session import AsrStreamSession
from app.audio.websocket_routes import as_json
from app.core.config import load_settings
from scripts.asr_file_smoke import run_smoke as run_asr_file_smoke
from scripts.asr_isolated_model_compare import select_best_run as select_best_isolated_asr_run


class FakeAsrEngine:
    provider = "fake-asr"
    model = "fake-model"

    async def start(self, *, sample_rate: int, language: str, mode: str) -> None:
        self.sample_rate = sample_rate
        self.language = language
        self.mode = mode

    async def accept_audio(self, pcm: bytes) -> list[AsrEvent]:
        return [AsrEvent(type="partial", text=f"bytes={len(pcm)}", is_final=False)]

    async def finish(self) -> list[AsrEvent]:
        return [AsrEvent(type="final", text="测试完成。", is_final=True)]


class FailingFileAsrEngine:
    provider = "fake-asr"
    model = "fake-model"

    def transcribe_file(self, audio_path: Path) -> str:
        raise RuntimeError("missing model")


class FakeFileAsrEngine:
    provider = "fake-asr"
    model = "fake-file-model"

    def transcribe_file(self, audio_path: Path) -> str:
        return "欢迎大家来体验语音识别模型。"


class TextFileAsrEngine:
    provider = "fake-asr"

    def __init__(self, model: str, text: str) -> None:
        self.model = model
        self.text = text

    def transcribe_file(self, audio_path: Path) -> str:
        return self.text


class EmotionalFileAsrEngine:
    provider = "fake-asr"

    def __init__(self, model: str, text: str, emotion: str) -> None:
        self.model = model
        self.text = text
        self.emotion = emotion

    def transcribe_file(self, audio_path: Path) -> AsrTranscriptionResult:
        return AsrTranscriptionResult(
            text=self.text,
            emotion=self.emotion,
            emotion_source="fake-emotion",
            emotion_confidence=0.82,
        )

def test_asr_file_presets_default_and_parser(monkeypatch) -> None:
    monkeypatch.delenv("ASR_FILE_PRESETS", raising=False)
    monkeypatch.delenv("ASR_REPAIR_PRESETS", raising=False)
    settings = load_settings()

    assert settings.asr_file_presets == "sensevoice-small"
    assert settings.asr_repair_presets == ""
    assert parse_asr_file_presets("sensevoice-small, fun-asr-nano") == [
        "sensevoice-small",
        "fun-asr-nano",
    ]
    assert parse_asr_file_presets(" , ") == ["sensevoice-small"]
    assert parse_optional_asr_presets(" , ") == []
    assert parse_optional_asr_presets("fun-asr-nano") == ["fun-asr-nano"]

def test_funasr_extract_text_handles_common_result_shapes() -> None:
    assert extract_text("你好") == "你好"
    assert extract_text({"text": "你好"}) == "你好"
    assert extract_text([{"text": "你"}, {"text": "好"}]) == "你好"

def test_funasr_clean_asr_text_removes_sensevoice_tags() -> None:
    text = "< | zh | > < | NEUTRAL | > < | Speech | > 欢 迎大家。。"

    assert clean_asr_text(text) == "欢迎大家。"

def test_asr_quality_detects_mojibake_and_clean_chinese() -> None:
    clean = evaluate_asr_text_quality("欢迎大家来体验语音识别模型。")
    broken = evaluate_asr_text_quality("������")
    punctuation_collision = evaluate_asr_text_quality("这是一个景象。，树上有桃子。")

    assert clean.passed is True
    assert clean.score == 1.0
    assert broken.passed is False
    assert "mojibake_or_replacement_char" in broken.reasons
    assert "low_chinese_ratio" in broken.reasons
    assert punctuation_collision.passed is False
    assert "punctuation_collision" in punctuation_collision.reasons

def test_audio_chat_input_cleans_punctuation_collision_without_clarifying() -> None:
    asr = AsrFileResponse(
        text="成，那就唠唠，。你最近有没有碰上什么怪事？，",
        provider="fake-asr",
        model="fake-model",
        audio_path="sample.wav",
        latency_ms=1.0,
        quality_passed=False,
        quality_score=0.65,
        quality_reasons=["punctuation_collision"],
    )

    prepared = prepare_audio_chat_input(asr)

    assert prepared.text == "成，那就唠唠。你最近有没有碰上什么怪事？"
    assert prepared.should_clarify is False
    assert clean_asr_text_for_chat("开放时间早上9点至下午5点，。") == "开放时间早上9点至下午5点。"

def test_audio_chat_input_clarifies_broken_or_overlong_text() -> None:
    broken = AsrFileResponse(
        text="������",
        provider="fake-asr",
        model="fake-model",
        audio_path="sample.wav",
        latency_ms=1.0,
        quality_passed=False,
        quality_score=0.0,
        quality_reasons=["mojibake_or_replacement_char", "low_chinese_ratio"],
    )
    overlong = AsrFileResponse(
        text="今天天气不错" * 20,
        provider="fake-asr",
        model="fake-model",
        audio_path="sample.wav",
        latency_ms=1.0,
    )

    assert prepare_audio_chat_input(broken).should_clarify is True
    assert prepare_audio_chat_input(overlong).clarify_reasons == ["too_long_for_realtime_chat"]

def test_funasr_extract_transcription_result_keeps_sensevoice_emotion() -> None:
    result = extract_transcription_result(
        {"text": "< | zh | > < | HAPPY | > < | Speech | > hello"}
    )

    assert result.text == "hello"
    assert result.emotion == "happy"
    assert result.emotion_source == "sensevoice_tag"

def test_emotion2vec_result_parser_selects_highest_scoring_emotion() -> None:
    result = parse_emotion2vec_result(
        [
            {
                "labels": ["生气/angry", "开心/happy", "中性/neutral"],
                "scores": [0.1, 0.87, 0.03],
            }
        ]
    )

    assert result.emotion == "happy"
    assert result.emotion_source == "emotion2vec"
    assert result.emotion_confidence == 0.87
    assert normalize_emotion_label("难过/sad") == "sad"

def test_modelscope_models_resolve_to_project_local_paths() -> None:
    if not Path("data/models/modelscope/iic/emotion2vec_plus_large").exists():
        pytest.skip("local ModelScope models are not downloaded; path resolution is only asserted with them present")
    resolved = resolve_modelscope_model("iic/emotion2vec_plus_large")
    vad = resolve_funasr_aux_model("fsmn-vad")

    assert "HutaoChatCore" in resolved
    assert resolved.endswith("data\\models\\modelscope\\iic\\emotion2vec_plus_large")
    assert vad is not None
    assert vad.endswith("data\\models\\modelscope\\iic\\speech_fsmn_vad_zh-cn-16k-common-pytorch")

def test_asr_pipeline_selects_best_quality_candidate(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")

    result = transcribe_with_candidates(
        audio_path,
        [
            NamedFileAsrEngine(
                id="weak",
                preset="weak-model",
                engine=TextFileAsrEngine("weak-model", "������"),
            ),
            NamedFileAsrEngine(
                id="strong",
                preset="strong-model",
                engine=TextFileAsrEngine("strong-model", "欢迎大家来体验语音识别模型。"),
            ),
        ],
    )

    assert result.selected_candidate_id == "strong"
    assert result.selection_reason == "best_quality_passed"
    assert result.text == "欢迎大家来体验语音识别模型。"
    assert result.quality_passed is True
    assert len(result.candidates) == 2
    assert result.candidates[0].quality_passed is False

def test_asr_pipeline_preserves_selected_candidate_emotion(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")

    result = transcribe_with_candidates(
        audio_path,
        [
            NamedFileAsrEngine(
                id="primary",
                preset="emotional-model",
                engine=EmotionalFileAsrEngine(
                    "emotional-model",
                    "欢迎大家来体验语音识别模型。",
                    "happy",
                ),
            ),
        ],
    )

    assert result.emotion == "happy"
    assert result.emotion_source == "fake-emotion"
    assert result.emotion_confidence == 0.82
    assert result.candidates[0].emotion == "happy"

def test_audio_emotion_enrichment_overrides_asr_emotion(monkeypatch, tmp_path: Path) -> None:
    class FakeEmotionEngine:
        def analyze_file(self, audio_path: Path) -> AudioEmotionResult:
            return AudioEmotionResult(
                emotion="angry",
                emotion_source="emotion2vec",
                emotion_confidence=0.91,
            )

    monkeypatch.setenv("AUDIO_EMOTION_ENABLED", "true")
    monkeypatch.setenv("AUDIO_EMOTION_MODEL", "fake-emotion-model")
    monkeypatch.setattr("app.audio.file_service.get_emotion_engine", lambda model: FakeEmotionEngine())
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    result = AsrFileResponse(
        text="欢迎大家来体验语音识别模型。",
        provider="fake-asr",
        model="fake-file-model",
        audio_path=str(audio_path),
        latency_ms=1.0,
        emotion="neutral",
        emotion_source="sensevoice_tag",
    )

    enriched = enrich_with_audio_emotion(audio_path, result)

    assert enriched.emotion == "angry"
    assert enriched.emotion_source == "emotion2vec"
    assert enriched.emotion_confidence == 0.91


def test_audio_emotion_initialization_failure_preserves_asr_result(monkeypatch, tmp_path: Path) -> None:
    class FailingEmotionEngine:
        def analyze_file(self, audio_path: Path) -> AudioEmotionResult:
            raise OSError("torch native runtime unavailable")

    monkeypatch.setenv("AUDIO_EMOTION_ENABLED", "true")
    monkeypatch.setattr(
        "app.audio.file_service.get_emotion_engine",
        lambda model: FailingEmotionEngine(),
    )
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    original = AsrFileResponse(
        text="测试文本",
        provider="fake",
        model="fake",
        audio_path=str(audio_path),
        latency_ms=1.0,
        quality_passed=True,
        quality_score=1.0,
        quality_reasons=[],
        emotion="neutral",
        emotion_source="sensevoice_tag",
        emotion_confidence=0.75,
    )

    assert enrich_with_audio_emotion(audio_path, original) is original
    assert original.emotion == "neutral"

def test_asr_pipeline_runs_repair_only_when_primary_quality_fails(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    repair_engine = TextFileAsrEngine("repair-model", "欢迎大家来体验语音识别模型。")

    good_primary = transcribe_with_repair_candidates(
        audio_path,
        [
            NamedFileAsrEngine(
                id="primary",
                preset="primary-model",
                engine=TextFileAsrEngine("primary-model", "欢迎大家来体验语音识别模型。"),
            )
        ],
        [NamedFileAsrEngine(id="repair", preset="repair-model", engine=repair_engine)],
    )
    bad_primary = transcribe_with_repair_candidates(
        audio_path,
        [
            NamedFileAsrEngine(
                id="primary",
                preset="primary-model",
                engine=TextFileAsrEngine("primary-model", "这是一个景象。，树上有桃子。"),
            )
        ],
        [NamedFileAsrEngine(id="repair", preset="repair-model", engine=repair_engine)],
    )

    assert good_primary.repair_attempted is False
    assert len(good_primary.candidates) == 1
    assert bad_primary.repair_attempted is True
    assert bad_primary.selected_candidate_id == "repair"
    assert len(bad_primary.candidates) == 2

def test_asr_isolated_compare_selects_best_non_timeout_run() -> None:
    selected = select_best_isolated_asr_run(
        [
            {
                "preset": "fun-asr-nano",
                "text": "",
                "quality_passed": False,
                "quality_score": 0.0,
                "latency_ms": 180000.0,
                "quality_reasons": ["timeout"],
                "timed_out": True,
            },
            {
                "preset": "sensevoice-small",
                "text": "欢迎大家来体验语音识别模型。",
                "quality_passed": True,
                "quality_score": 1.0,
                "latency_ms": 900.0,
                "quality_reasons": [],
                "timed_out": False,
            },
        ]
    )

    assert selected["preset"] == "sensevoice-small"

def test_transcribe_audio_file_returns_primary_candidate(tmp_path: Path) -> None:
    from app.audio.file_service import transcribe_audio_file

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")

    result = transcribe_audio_file(audio_path, engine=FakeFileAsrEngine())

    assert result.selected_candidate_id == "primary"
    assert result.selection_reason == "single_candidate"
    assert len(result.candidates) == 1
    assert result.candidates[0].text == "欢迎大家来体验语音识别模型。"

def test_funasr_file_engine_reports_missing_dependency(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    engine = FunAsrFileEngine()
    original_import = __builtins__["__import__"]

    def fake_import(name, *args, **kwargs):
        if name == "funasr":
            raise ImportError("no funasr")
        return original_import(name, *args, **kwargs)

    monkeypatch.setitem(__builtins__, "__import__", fake_import)

    try:
        engine.transcribe_file(audio_path)
    except FunAsrUnavailableError as exc:
        assert "FunASR is not installed" in str(exc)
    else:
        raise AssertionError("missing funasr should raise FunAsrUnavailableError")

def test_asr_stream_session_emits_partial_and_final() -> None:
    session = AsrStreamSession(FakeAsrEngine())

    start_events = asyncio.run(session.start(sample_rate=16000, language="zh", mode="2pass"))
    partial_events = asyncio.run(session.accept_audio(b"1234"))
    final_events = asyncio.run(session.finish())

    assert start_events == []
    assert partial_events[0].type == "partial"
    assert partial_events[0].text == "bytes=4"
    assert final_events[0].type == "final"
    assert final_events[0].text == "测试完成。"

def test_asr_event_json_shape() -> None:
    payload = json.loads(as_json(AsrEvent(type="partial", text="你好", is_final=False)))

    assert payload["type"] == "partial"
    assert payload["text"] == "你好"
    assert payload["is_final"] is False

def test_asr_file_smoke_writes_failure_report(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "id": "sample-1",
                    "path": str(audio_path),
                    "expected_contains": ["你好"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report_path = run_asr_file_smoke(
        manifest_path=manifest_path,
        output_root=tmp_path / "logs",
        engine=FailingFileAsrEngine(),
    )
    result = json.loads((report_path.parent / "asr-file-smoke-result.json").read_text(encoding="utf-8"))

    assert result["status"] == "FAIL"
    assert result["failed_count"] == 1
    assert "missing model" in result["results"][0]["error"]
    assert report_path.exists()
