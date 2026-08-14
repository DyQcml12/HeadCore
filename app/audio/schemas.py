from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import ChatResponse


AsrEventType = Literal["partial", "final", "error"]


@dataclass(frozen=True)
class AsrEvent:
    type: AsrEventType
    text: str
    is_final: bool
    start_ms: int | None = None
    end_ms: int | None = None
    confidence: float | None = None


class AsrCandidateResponse(BaseModel):
    id: str
    preset: str
    provider: str
    model: str
    text: str
    emotion: str | None = None
    emotion_source: str | None = None
    emotion_confidence: float | None = None
    latency_ms: float
    quality_passed: bool
    quality_score: float
    quality_reasons: list[str] = Field(default_factory=list)
    error: str | None = None


class AsrFileResponse(BaseModel):
    text: str
    provider: str
    model: str
    audio_path: str
    emotion: str | None = None
    emotion_source: str | None = None
    emotion_confidence: float | None = None
    latency_ms: float
    quality_passed: bool = True
    quality_score: float = 1.0
    quality_reasons: list[str] = Field(default_factory=list)
    error: str | None = None
    selected_candidate_id: str = "primary"
    selection_reason: str = "single_candidate"
    repair_attempted: bool = False
    candidates: list[AsrCandidateResponse] = Field(default_factory=list)


class AudioChatFileResponse(BaseModel):
    transcript_text: str
    chat_input_text: str
    chat_bypassed_due_to_asr_quality: bool = False
    chat_bypass_reasons: list[str] = Field(default_factory=list)
    reply_text: str
    asr: AsrFileResponse
    chat: ChatResponse


class PreparedAudioChatFileResponse(BaseModel):
    transcript_text: str
    chat_input_text: str
    chat_bypassed_due_to_asr_quality: bool = False
    chat_bypass_reasons: list[str] = Field(default_factory=list)
    clarification_reply: str | None = None
    asr: AsrFileResponse


class AsrStartMessage(BaseModel):
    type: Literal["start"]
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    language: str = Field(default="zh", max_length=16)
    mode: str = Field(default="2pass", max_length=32)
