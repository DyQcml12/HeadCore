from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from collections.abc import AsyncIterator
from typing import Any, Protocol, TypeVar, runtime_checkable


class ProviderCapability(StrEnum):
    TEXT = "text"
    ASR = "asr"
    TTS = "tts"


class ProviderHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    CIRCUIT_OPEN = "circuit_open"


class ProviderErrorCode(StrEnum):
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    MODEL_MISSING = "model_missing"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_FAILED = "authentication_failed"


@dataclass(frozen=True, order=True)
class ProviderId:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("provider id must be non-empty and contain no whitespace")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TextRequest:
    system_prompt: str
    user_prompt: str


@dataclass(frozen=True)
class AsrRequest:
    audio_path: Path
    language: str = "zh"


@dataclass(frozen=True)
class AsrResult:
    text: str
    emotion: str | None = None
    language: str | None = None
    confidence: float | None = None
    emotion_source: str | None = None
    emotion_confidence: float | None = None


@dataclass(frozen=True)
class TtsRequest:
    text: str
    output_path: Path
    emotion: str = ""
    user_input: str = ""


@runtime_checkable
class Provider(Protocol):
    provider_id: ProviderId
    capabilities: frozenset[ProviderCapability]


@runtime_checkable
class TextProvider(Provider, Protocol):
    async def generate_text(self, request: TextRequest) -> str: ...


@runtime_checkable
class StreamingTextProvider(TextProvider, Protocol):
    def stream_text(self, request: TextRequest) -> AsyncIterator[str]: ...


@runtime_checkable
class AsrProvider(Provider, Protocol):
    async def transcribe(self, request: AsrRequest) -> AsrResult: ...


@runtime_checkable
class TtsProvider(Provider, Protocol):
    async def synthesize(self, request: TtsRequest) -> Path: ...


class ProviderError(RuntimeError):
    def __init__(
        self,
        code: ProviderErrorCode,
        message: str = "",
        *,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or code.value)
        self.code = code
        self.retryable = code in {
            ProviderErrorCode.UNAVAILABLE,
            ProviderErrorCode.TIMEOUT,
            ProviderErrorCode.RATE_LIMITED,
        } if retryable is None else retryable
        self.details = details or {}


@dataclass(frozen=True)
class ProviderAttempt:
    provider_id: ProviderId
    capability: ProviderCapability
    attempt: int
    started_at: float
    duration_seconds: float
    success: bool
    error_code: ProviderErrorCode | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderTrace:
    capability: ProviderCapability
    attempts: tuple[ProviderAttempt, ...]


T = TypeVar("T")


@dataclass(frozen=True)
class RoutingDecision:
    provider_id: ProviderId
    value: T
    trace: ProviderTrace
