from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from app.channels.contracts import ChannelEvent, ChannelEventType
from app.schemas import ChatResponse


class HeadChatService(Protocol):
    async def reply(self, user_input: str, **kwargs: object) -> ChatResponse: ...

    def stream_reply(self, user_input: str, **kwargs: object) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class HeadRuntimeContext:
    subject_id: str
    session_id: str
    input_source: Literal["text", "audio", "image"] = "text"
    input_quality_passed: bool = True
    input_quality_reasons: tuple[str, ...] = ()
    input_emotion: str | None = None
    input_emotion_source: str | None = None
    input_emotion_confidence: float | None = None
    response_style_instruction: str | None = None
    sandbox_persona_id: str | None = None


class UnsupportedHeadEventError(ValueError):
    pass


class HeadRuntime:
    """The single cognitive entry point above channel and model details."""

    def __init__(self, chat_service: HeadChatService) -> None:
        self._chat_service = chat_service

    async def handle(self, event: ChannelEvent, context: HeadRuntimeContext) -> ChatResponse:
        text, kwargs = self._prepare_call(event, context)
        return await self._chat_service.reply(text, **kwargs)

    async def stream(
        self,
        event: ChannelEvent,
        context: HeadRuntimeContext,
    ) -> AsyncIterator[str]:
        text, kwargs = self._prepare_call(event, context)
        async for chunk in self._chat_service.stream_reply(text, **kwargs):
            yield chunk

    @staticmethod
    def _prepare_call(
        event: ChannelEvent,
        context: HeadRuntimeContext,
    ) -> tuple[str, dict[str, object]]:
        if event.event_type != ChannelEventType.MESSAGE or event.message is None:
            raise UnsupportedHeadEventError("HeadRuntime currently accepts message events only")
        source_platform = event.metadata.get("source_platform")
        platform = str(source_platform).strip() if source_platform else None
        platform_user_id = event.identity.user_id if platform else None
        return event.message.text, {
            "session_id": context.session_id,
            "user_id": context.subject_id,
            "platform": platform,
            "platform_user_id": platform_user_id,
            "platform_group_id": event.thread.group_id,
            "response_style_instruction": context.response_style_instruction,
            "input_source": context.input_source,
            "input_quality_passed": context.input_quality_passed,
            "input_quality_reasons": list(context.input_quality_reasons),
            "input_emotion": context.input_emotion,
            "input_emotion_source": context.input_emotion_source,
            "input_emotion_confidence": context.input_emotion_confidence,
            "head_runtime_origin": "channel_event",
            "sandbox_persona_id": context.sandbox_persona_id,
        }
