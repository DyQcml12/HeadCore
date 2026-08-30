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


class AudioUploadValidationError(ValueError):
    """Raised when an uploaded audio file violates the local upload policy."""

    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


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


def _csv_values(raw_value: str) -> set[str]:
    return {item.strip().lower() for item in raw_value.split(",") if item.strip()}


async def save_upload_to_temp(
    upload: UploadFile,
    *,
    max_bytes: int | None = None,
    allowed_extensions: str | None = None,
    allowed_content_types: str | None = None,
) -> Path:
    settings = load_settings()
    max_bytes = settings.audio_upload_max_bytes if max_bytes is None else max_bytes
    allowed_extensions = (
        settings.audio_upload_allowed_extensions
        if allowed_extensions is None
        else allowed_extensions
    )
    allowed_content_types = (
        settings.audio_upload_allowed_content_types
        if allowed_content_types is None
        else allowed_content_types
    )

    filename = upload.filename or "audio.wav"
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {
        item if item.startswith(".") else "." + item
        for item in _csv_values(allowed_extensions)
    }
    if allowed_suffixes and suffix not in allowed_suffixes:
        raise AudioUploadValidationError(
            "unsupported audio file extension",
            status_code=415,
        )

    content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    allowed_types = _csv_values(allowed_content_types)
    # Some clients send application/octet-stream for a valid audio filename;
    # extension validation still applies, so an absent/generic type is allowed.
    if (
        content_type
        and content_type not in allowed_types
        and content_type != "application/octet-stream"
    ):
        raise AudioUploadValidationError(
            "unsupported audio content type",
            status_code=415,
        )
    if max_bytes <= 0:
        raise AudioUploadValidationError(
            "audio upload limit is not configured",
            status_code=500,
        )

    temp_path: Path | None = None
    total_bytes = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".wav") as tmp:
            temp_path = Path(tmp.name)
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise AudioUploadValidationError(
                        f"audio upload exceeds {max_bytes} bytes",
                        status_code=413,
                    )
                tmp.write(chunk)
        if total_bytes == 0:
            raise AudioUploadValidationError("audio upload is empty", status_code=400)
        return temp_path
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def warmup_audio_pipeline() -> None:
    """Preload ASR and emotion engines so the first request is fast.

    Model loading costs tens of seconds on a cold process (measured ~74s for
    SenseVoice + emotion2vec). Running this in a background thread at startup
    turns that into a one-time, invisible cost; failures only log a warning
    because models may simply be absent on fresh deployments.
    """
    import logging
    import wave

    logger = logging.getLogger("hutao.audio.warmup")
    try:
        build_default_file_asr_engines()
        logger.info("asr engine warmup complete")
    except Exception:
        logger.warning("asr engine warmup failed (models may be absent)", exc_info=True)
    try:
        settings = load_settings()
        if settings.audio_emotion_enabled:
            engine = get_emotion_engine(settings.audio_emotion_model)
            probe = Path(tempfile.gettempdir()) / "hutao_warmup_probe.wav"
            with wave.open(str(probe), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 8000)
            try:
                engine.analyze_file(probe)
            finally:
                probe.unlink(missing_ok=True)
            logger.info("emotion engine warmup complete")
    except Exception:
        logger.warning("emotion engine warmup failed (models may be absent)", exc_info=True)


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
