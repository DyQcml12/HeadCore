from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_input: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", max_length=128)
    user_id: str = Field(default="default-user", max_length=128)
    platform: str | None = Field(default=None, max_length=32)
    platform_user_id: str | None = Field(default=None, max_length=128)
    platform_group_id: str | None = Field(default=None, max_length=128)
    response_style_instruction: str | None = Field(default=None, max_length=1000)
    persona_id: str | None = Field(default=None, min_length=1, max_length=128)
    input_source: Literal["text", "audio", "image"] = "text"
    input_quality_passed: bool = True
    input_quality_reasons: list[str] = Field(default_factory=list, max_length=20)
    input_emotion: str | None = Field(default=None, max_length=32)
    input_emotion_source: str | None = Field(default=None, max_length=64)
    input_emotion_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    text: str
    provider: str
    model: str
    used_live_api: bool
    fallback_used: bool = False
    error: str | None = None


class ChatHistoryMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatHistoryMessage]


class HealthResponse(BaseModel):
    status: str
    app_name: str
    provider: str
    model: str
    api_key_configured: bool


class PublicAuthStatusResponse(BaseModel):
    authentication_enabled: bool
    registration_enabled: bool
    password_reset_enabled: bool


class PublicWebVoiceStatusResponse(BaseModel):
    enabled: bool
    max_reply_chars: int
    provider_ready: bool = False
    provider: str = "gpt_sovits"
    base_url: str = ""


class WebVoiceSynthesisRequest(BaseModel):
    reply_id: str = Field(min_length=16, max_length=128)
    session_id: str = Field(default="default", min_length=1, max_length=128)
    user_id: str = Field(default="default-user", min_length=1, max_length=128)


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    session_id: str | None
    memory_type: str
    content: str
    confidence: float | None
    created_at: str
    updated_at: str


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]


class DeleteMemoryResponse(BaseModel):
    deleted: bool


class DialogueContextResponse(BaseModel):
    status: Literal["ready", "tracking_task", "waiting_for_user"]
    active_task: str | None = None
    pending_question: str | None = None
