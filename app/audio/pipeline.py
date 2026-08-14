from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.audio.quality import evaluate_asr_text_quality
from app.audio.schemas import AsrCandidateResponse, AsrFileResponse
from app.core.security import redact_secrets


class FileAsrEngine(Protocol):
    provider: str
    model: str

    def transcribe_file(self, audio_path: Path) -> object:
        pass


@dataclass(frozen=True)
class NamedFileAsrEngine:
    id: str
    preset: str
    engine: FileAsrEngine


def transcribe_with_candidates(
    audio_path: Path,
    engines: list[NamedFileAsrEngine],
) -> AsrFileResponse:
    if not engines:
        raise ValueError("At least one ASR engine is required.")

    candidates = [run_candidate(audio_path, item) for item in engines]
    selected = select_best_candidate(candidates)
    return build_asr_file_response(
        audio_path=audio_path,
        candidates=candidates,
        repair_attempted=False,
    )


def transcribe_with_repair_candidates(
    audio_path: Path,
    primary_engines: list[NamedFileAsrEngine],
    repair_engines: list[NamedFileAsrEngine],
) -> AsrFileResponse:
    if not primary_engines:
        raise ValueError("At least one primary ASR engine is required.")

    candidates = [run_candidate(audio_path, item) for item in primary_engines]
    selected = select_best_candidate(candidates)
    repair_attempted = False
    if not selected.quality_passed and repair_engines:
        repair_attempted = True
        candidates.extend(run_candidate(audio_path, item) for item in repair_engines)
    return build_asr_file_response(
        audio_path=audio_path,
        candidates=candidates,
        repair_attempted=repair_attempted,
    )


def build_asr_file_response(
    *,
    audio_path: Path,
    candidates: list[AsrCandidateResponse],
    repair_attempted: bool,
) -> AsrFileResponse:
    selected = select_best_candidate(candidates)
    return AsrFileResponse(
        text=selected.text,
        provider=selected.provider,
        model=selected.model,
        audio_path=str(audio_path),
        emotion=selected.emotion,
        emotion_source=selected.emotion_source,
        emotion_confidence=selected.emotion_confidence,
        latency_ms=sum(candidate.latency_ms for candidate in candidates),
        quality_passed=selected.quality_passed,
        quality_score=selected.quality_score,
        quality_reasons=selected.quality_reasons,
        error=selected.error,
        selected_candidate_id=selected.id,
        selection_reason=build_selection_reason(selected, candidates),
        repair_attempted=repair_attempted,
        candidates=candidates,
    )


def run_candidate(audio_path: Path, named_engine: NamedFileAsrEngine) -> AsrCandidateResponse:
    started_at = time.perf_counter()
    text = ""
    emotion = None
    emotion_source = None
    emotion_confidence = None
    error = None
    try:
        transcription = named_engine.engine.transcribe_file(audio_path)
        text = extract_candidate_text(transcription)
        emotion = extract_optional_string(transcription, "emotion")
        emotion_source = extract_optional_string(transcription, "emotion_source")
        emotion_confidence = extract_optional_float(transcription, "emotion_confidence")
    except Exception as exc:
        error = redact_secrets(str(exc))
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    quality = evaluate_asr_text_quality(text)
    if error and "engine_error" not in quality.reasons:
        quality_reasons = [*quality.reasons, "engine_error"]
        quality_passed = False
        quality_score = 0.0
    else:
        quality_reasons = quality.reasons
        quality_passed = quality.passed
        quality_score = quality.score
    return AsrCandidateResponse(
        id=named_engine.id,
        preset=named_engine.preset,
        provider=named_engine.engine.provider,
        model=named_engine.engine.model,
        text=text,
        emotion=emotion,
        emotion_source=emotion_source,
        emotion_confidence=emotion_confidence,
        latency_ms=latency_ms,
        quality_passed=quality_passed,
        quality_score=quality_score,
        quality_reasons=quality_reasons,
        error=error,
    )


def extract_candidate_text(transcription: object) -> str:
    if isinstance(transcription, str):
        return transcription
    text = getattr(transcription, "text", "")
    return text if isinstance(text, str) else str(text)


def extract_optional_string(transcription: object, field_name: str) -> str | None:
    value = getattr(transcription, field_name, None)
    if isinstance(value, str) and value:
        return value
    return None


def extract_optional_float(transcription: object, field_name: str) -> float | None:
    value = getattr(transcription, field_name, None)
    if isinstance(value, int | float):
        return float(value)
    return None


def select_best_candidate(candidates: list[AsrCandidateResponse]) -> AsrCandidateResponse:
    return sorted(
        candidates,
        key=lambda item: (
            item.quality_passed,
            item.quality_score,
            bool(item.text.strip()),
            -item.latency_ms,
        ),
        reverse=True,
    )[0]


def build_selection_reason(
    selected: AsrCandidateResponse,
    candidates: list[AsrCandidateResponse],
) -> str:
    if len(candidates) == 1:
        return "single_candidate"
    if selected.quality_passed:
        return "best_quality_passed"
    return "best_available_low_quality"
