from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.channels.contracts import ChannelAttachment


class PerceptionModality(StrEnum):
    AUDIO = "audio"
    IMAGE = "image"
    FILE = "file"
    METADATA = "metadata"


class PerceptionQuality(StrEnum):
    GOOD = "good"
    UNCERTAIN = "uncertain"
    DEGRADED = "degraded"
    CONFLICTED = "conflicted"
    FAILED = "failed"


ObservationQuality = Literal["good", "uncertain", "degraded", "conflicted", "failed"]


class MemoryDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


class PerceptionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)


class PerceptionInput(PerceptionContract):
    modality: PerceptionModality
    source: str = Field(min_length=1, max_length=128)
    local_path: Path | None = None
    attachment: ChannelAttachment | None = None
    remote_url: str | None = Field(default=None, max_length=2048)
    declared_mime: str | None = Field(default=None, max_length=128)
    declared_size_bytes: int | None = Field(default=None, ge=0)
    mime_type: str | None = Field(default=None, max_length=128)
    size_bytes: int | None = Field(default=None, ge=0)
    attachment_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_single_payload(self) -> PerceptionInput:
        present = sum(value is not None for value in (self.local_path, self.attachment, self.remote_url))
        if present != 1:
            raise ValueError("exactly one input payload is required")
        return self


class ProviderTrace(PerceptionContract):
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(default="", max_length=256)
    latency_ms: float = Field(default=0.0, ge=0)
    fallback: bool = False
    success: bool = True
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=500)


class MemoryEligibility(PerceptionContract):
    decision: MemoryDecision
    reasons: tuple[str, ...] = ()


class PerceptionObservation(PerceptionContract):
    modality: PerceptionModality
    source: str = Field(default="", max_length=128)
    text: str = Field(default="", max_length=10000)
    objects: tuple[str, ...] = ()
    emotion: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=32)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    quality: PerceptionQuality = PerceptionQuality.FAILED
    quality_reasons: tuple[str, ...] = ()
    traces: tuple[ProviderTrace, ...] = ()
    memory_eligibility: MemoryEligibility = Field(
        default_factory=lambda: MemoryEligibility(
            decision=MemoryDecision.DENY,
            reasons=("no_reliable_observation",),
        )
    )
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.quality != PerceptionQuality.FAILED

    @property
    def memory(self) -> MemoryEligibility:
        return self.memory_eligibility


class ProviderOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str = ""
    objects: tuple[str, ...] = ()
    emotion: str | None = None
    language: str | None = None
    confidence: float | None = None
    quality_reasons: tuple[str, ...] = ()

    @classmethod
    def from_value(cls, value: Any) -> ProviderOutput:
        if isinstance(value, str):
            return cls(text=value)
        if isinstance(value, dict):
            return cls.model_validate(value)
        data = {
            key: getattr(value, key)
            for key in ("text", "objects", "emotion", "language", "confidence", "quality_reasons")
            if hasattr(value, key)
        }
        if "text" not in data and hasattr(value, "summary"):
            data["text"] = getattr(value, "summary")
        return cls.model_validate(data)


ErrorCode = Literal[
    "invalid_input",
    "invalid_mime",
    "input_too_large",
    "path_not_allowed",
    "private_network_url",
    "model_missing",
    "provider_unavailable",
    "timeout",
    "invalid_response",
]
