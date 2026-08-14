from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.audio.funasr_engine import FunAsrUnavailableError
from app.core.security import redact_secrets
from app.providers.contracts import (
    AsrRequest,
    AsrResult,
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderId,
)


@dataclass(frozen=True)
class FunAsrProvider:
    provider_id: ProviderId
    engine: object
    capabilities: frozenset[ProviderCapability] = field(
        default_factory=lambda: frozenset({ProviderCapability.ASR})
    )

    async def transcribe(self, request: AsrRequest) -> AsrResult:
        try:
            raw = await asyncio.to_thread(self.engine.transcribe_file, request.audio_path)  # type: ignore[attr-defined]
        except FunAsrUnavailableError as exc:
            raise ProviderError(ProviderErrorCode.MODEL_MISSING, "FunASR model is unavailable") from exc
        except FileNotFoundError as exc:
            raise ProviderError(ProviderErrorCode.MODEL_MISSING, "FunASR model or input is missing") from exc
        except TimeoutError as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "FunASR transcription timed out") from exc
        except Exception as exc:
            message = redact_secrets(str(exc))
            if "model" in message.lower() and any(
                marker in message.lower() for marker in ("missing", "not found", "does not exist")
            ):
                raise ProviderError(ProviderErrorCode.MODEL_MISSING, message) from exc
            raise ProviderError(
                ProviderErrorCode.UNAVAILABLE,
                message or "FunASR transcription failed",
                details={"exception_type": type(exc).__name__},
            ) from exc
        text = str(raw if isinstance(raw, str) else getattr(raw, "text", "")).strip()
        if not text:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE, "FunASR returned empty text")
        return AsrResult(
            text=text,
            emotion=_optional_text(raw, "emotion"),
            language=_optional_text(raw, "language") or request.language,
            confidence=_optional_float(raw, "confidence"),
            emotion_source=_optional_text(raw, "emotion_source"),
            emotion_confidence=_optional_float(raw, "emotion_confidence"),
        )


def _optional_text(value: object, name: str) -> str | None:
    item = getattr(value, name, None)
    return str(item).strip() if item else None


def _optional_float(value: object, name: str) -> float | None:
    item = getattr(value, name, None)
    return float(item) if isinstance(item, int | float) else None
