from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.channels.adapters import CoreApiEventAdapter
from app.core.config import load_settings
from app.head.runtime import HeadRuntime, HeadRuntimeContext
from app.services.chat_service import ChatService
from app.storage.v2_runtime import (
    build_database_v2_chat_repository,
    database_v2_chat_user_id,
    should_use_database_v2,
    try_handle_database_v2_platform_message,
)


settings = load_settings()
router = APIRouter(tags=["openai-compatible"])


class OpenAIMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = ""


class OpenAIChatCompletionRequest(BaseModel):
    model: str = Field(default="hutao-chatcore")
    messages: list[OpenAIMessage] = Field(min_length=1)
    stream: bool = False
    user: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    platform: str | None = None
    platform_user_id: str | None = None
    platform_group_id: str | None = None


@router.get("/v1/models")
async def list_models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": "hutao-chatcore",
                "object": "model",
                "created": 0,
                "owned_by": "hutao-chatcore",
            },
            {
                "id": settings.model_name,
                "object": "model",
                "created": 0,
                "owned_by": settings.model_provider,
            },
        ],
    }


@router.post("/v1/chat/completions")
async def create_chat_completion(request: OpenAIChatCompletionRequest):
    user_input = extract_latest_user_message(request.messages)
    session_id = request.session_id or build_compat_session_id(request)
    user_id = request.user_id or request.user or "openai-compat-user"

    v2_response = await try_handle_database_v2_platform_message(
        settings=settings,
        platform=request.platform,
        platform_user_id=request.platform_user_id,
        platform_group_id=request.platform_group_id,
        message_text=user_input,
    )
    if v2_response is not None:
        if request.stream:
            return StreamingResponse(
                stream_static_openai_reply(
                    model=request.model,
                    content=v2_response.text,
                    finish_reason="stop",
                ),
                media_type="text/event-stream; charset=utf-8",
            )
        return build_chat_completion_response(
            model=request.model,
            content=v2_response.text,
            finish_reason="stop",
        )
    use_v2_chat_storage = should_use_database_v2(
        settings,
        platform=request.platform,
        platform_user_id=request.platform_user_id,
    )
    chat_user_id = (
        database_v2_chat_user_id(
            platform=request.platform,
            platform_user_id=request.platform_user_id,
            fallback_user_id=user_id,
        )
        if use_v2_chat_storage
        else user_id
    )
    runtime = HeadRuntime(
        ChatService(settings, repository=build_database_v2_chat_repository(settings))
        if use_v2_chat_storage
        else ChatService(settings)
    )
    event = build_openai_channel_event(request, user_input, session_id, user_id)
    context = HeadRuntimeContext(subject_id=chat_user_id, session_id=session_id)
    if request.stream:
        return StreamingResponse(
            stream_openai_reply(
                runtime=runtime,
                event=event,
                context=context,
                request=request,
            ),
            media_type="text/event-stream; charset=utf-8",
        )

    response = await runtime.handle(event, context)
    return build_chat_completion_response(
        model=request.model,
        content=response.text,
        finish_reason="stop",
    )


def extract_latest_user_message(messages: list[OpenAIMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            content = normalize_message_content(message.content)
            if content:
                return content
    raise HTTPException(status_code=400, detail="messages must include a non-empty user message")


def normalize_message_content(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(str(item["text"]).strip())
    return "\n".join(part for part in parts if part).strip()


def build_compat_session_id(request: OpenAIChatCompletionRequest) -> str:
    if request.platform and request.platform_user_id:
        return f"{request.platform}-compat-{request.platform_user_id}"
    if request.user:
        return f"openai-compat-{request.user}"
    return "openai-compat-default"


def build_chat_completion_response(
    *,
    model: str,
    content: str,
    finish_reason: str | None,
) -> dict[str, object]:
    return {
        "id": "chatcmpl-hutao-" + str(int(time.time() * 1000)),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


async def stream_openai_reply(
    *,
    runtime: HeadRuntime,
    event,  # type: ignore[no-untyped-def]
    context: HeadRuntimeContext,
    request: OpenAIChatCompletionRequest,
) -> AsyncIterator[str]:
    async for chunk in runtime.stream(event, context):
        yield "data: " + json.dumps(
            {
                "id": "chatcmpl-hutao-stream",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None,
                    }
                ],
            },
            ensure_ascii=False,
        ) + "\n\n"
    yield "data: " + json.dumps(
        {
            "id": "chatcmpl-hutao-stream",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        },
        ensure_ascii=False,
    ) + "\n\n"
    yield "data: [DONE]\n\n"


def build_openai_channel_event(
    request: OpenAIChatCompletionRequest,
    user_input: str,
    session_id: str,
    user_id: str,
):  # type: ignore[no-untyped-def]
    return CoreApiEventAdapter().adapt(
        {
            "user_input": user_input,
            "session_id": session_id,
            "user_id": user_id,
            "platform": request.platform,
            "platform_user_id": request.platform_user_id,
            "platform_group_id": request.platform_group_id,
        }
    )


async def stream_static_openai_reply(
    *,
    model: str,
    content: str,
    finish_reason: str | None,
) -> AsyncIterator[str]:
    yield "data: " + json.dumps(
        {
            "id": "chatcmpl-hutao-stream",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content},
                    "finish_reason": None,
                }
            ],
        },
        ensure_ascii=False,
    ) + "\n\n"
    yield "data: " + json.dumps(
        {
            "id": "chatcmpl-hutao-stream",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": finish_reason,
                }
            ],
        },
        ensure_ascii=False,
    ) + "\n\n"
    yield "data: [DONE]\n\n"
