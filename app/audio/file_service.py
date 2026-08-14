from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import UploadFile

from app.core.config import load_settings
from app.audio.emotion_engine import Emotion2VecEngine
from app.audio.funasr_engine import FunAsrFileEngine
from app.audio.pipeline import NamedFileAsrEngine, transcribe_with_candidates
from app.audio.pipeline import transcribe_with_repair_candidates
from app.audio.provider_routing import RoutedFileAsrEngine
from app.audio.schemas import AsrFileResponse


_ENGINES: dict[str, FunAsrFileEngine] = {}
_EMOTION_ENGINES: dict[str, Emotion2VecEngine] = {}
_ROUTED_ENGINES: dict[str, RoutedFileAsrEngine] = {}


def parse_asr_file_presets(raw_value: str) -> list[str]:
    presets = [item.strip() for item in raw_value.split(",") if item.strip()]
    return presets or ["sensevoice-small"]


def parse_optional_asr_presets(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def get_engine_for_preset(preset: str) -> FunAsrFileEngine:
    if preset not in _ENGINES:
        _ENGINES[preset] = FunAsrFileEngine.from_preset(preset)
    return _ENGINES[preset]


def get_emotion_engine(model: str) -> Emotion2VecEngine:
    if model not in _EMOTION_ENGINES:
        _EMOTION_ENGINES[model] = Emotion2VecEngine(model=model)
    return _EMOTION_ENGINES[model]


def build_default_file_asr_engines() -> list[NamedFileAsrEngine]:
    settings = load_settings()
    return build_file_asr_engines(parse_asr_file_presets(settings.asr_file_presets))


def build_default_repair_asr_engines() -> list[NamedFileAsrEngine]:
    settings = load_settings()
    return build_file_asr_engines(parse_optional_asr_presets(settings.asr_repair_presets))


def build_file_asr_engines(presets: list[str]) -> list[NamedFileAsrEngine]:
    settings = load_settings()
    return [
        NamedFileAsrEngine(
            id=preset,
            preset=preset,
            engine=get_routed_engine_for_preset(preset, settings),
        )
        for preset in presets
    ]


def get_routed_engine_for_preset(preset: str, settings) -> RoutedFileAsrEngine:
    if preset not in _ROUTED_ENGINES:
        _ROUTED_ENGINES[preset] = RoutedFileAsrEngine(
            get_engine_for_preset(preset),
            provider_id=f"funasr-{preset}",
            timeout_seconds=settings.asr_provider_timeout_seconds,
            circuit_failure_threshold=settings.asr_provider_circuit_failure_threshold,
            circuit_recovery_seconds=settings.asr_provider_circuit_recovery_seconds,
        )
    return _ROUTED_ENGINES[preset]


async def save_upload_to_temp(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        return Path(tmp.name)


def transcribe_audio_file(
    audio_path: Path,
    engine: FunAsrFileEngine | None = None,
    *,
    include_emotion: bool = True,
) -> AsrFileResponse:
    if engine:
        settings = load_settings()
        engines = [
            NamedFileAsrEngine(
                id="primary",
                preset="injected",
                engine=RoutedFileAsrEngine(
                    engine,
                    provider_id="funasr-injected",
                    timeout_seconds=settings.asr_provider_timeout_seconds,
                    circuit_failure_threshold=settings.asr_provider_circuit_failure_threshold,
                    circuit_recovery_seconds=settings.asr_provider_circuit_recovery_seconds,
                ),
            )
        ]
        return transcribe_with_candidates(audio_path, engines)
    result = transcribe_with_repair_candidates(
        audio_path=audio_path,
        primary_engines=build_default_file_asr_engines(),
        repair_engines=build_default_repair_asr_engines(),
    )
    return enrich_with_audio_emotion(audio_path, result) if include_emotion else result


def enrich_with_audio_emotion(audio_path: Path, result: AsrFileResponse) -> AsrFileResponse:
    settings = load_settings()
    if not settings.audio_emotion_enabled:
        return result
    try:
        emotion_result = get_emotion_engine(settings.audio_emotion_model).analyze_file(audio_path)
    except Exception:
        return result
    if not emotion_result.emotion:
        return result
    result.emotion = emotion_result.emotion
    result.emotion_source = emotion_result.emotion_source
    result.emotion_confidence = emotion_result.emotion_confidence
    return result
