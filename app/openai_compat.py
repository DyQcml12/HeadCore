from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Cookie, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.channels.adapters import CoreApiEventAdapter
from app.core.config import load_settings
from app.head.runtime import HeadRuntime, HeadRuntimeContext
from app.services.chat_service import ChatService
from app.services.model_client import get_shared_deepseek_client
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
async def create_chat_completion(
    request: OpenAIChatCompletionRequest,
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
):
    user_input = extract_latest_user_message(request.messages)
    user_id, session_id = await resolve_openai_identity(
        request,
        hutao_session=hutao_session,
        csrf_token=csrf_token,
        authorization=authorization,
    )

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
        ChatService(
            settings,
            client=get_shared_deepseek_client(settings),
            repository=build_database_v2_chat_repository(settings),
        )
        if use_v2_chat_storage
        else ChatService(settings, client=get_shared_deepseek_client(settings))
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
            raise HTTPException(status_code=400, detail="message content part must be an object")
        part_type = item.get("type")
        if part_type == "text" and isinstance(item.get("text"), str):
            parts.append(str(item["text"]).strip())
            continue
        if part_type in {"image_url", "input_image", "audio_url", "input_audio"}:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{part_type} content is not supported by the OpenAI-compatible endpoint; "
                    "use the local visual workbench or audio upload endpoints"
                ),
            )
        raise HTTPException(
            status_code=400,
            detail="unsupported message content part; only text content is supported",
        )
    return "\n".join(part for part in parts if part).strip()


def build_compat_session_id(request: OpenAIChatCompletionRequest) -> str:
    if request.platform and request.platform_user_id:
        return f"{request.platform}-compat-{request.platform_user_id}"
    if request.user:
        return f"openai-compat-{request.user}"
    return "openai-compat-default"


async def resolve_openai_identity(
    request: OpenAIChatCompletionRequest,
    *,
    hutao_session: str | None,
    csrf_token: str | None,
    authorization: str | None,
) -> tuple[str, str]:
    """Resolve request identity without trusting body fields in authenticated mode.

    The compatibility endpoint remains usable for local development while public
    web authentication is disabled. Once that switch is enabled, it follows the
    same session/CSRF or Bearer identity boundary as the web and mini-program
    APIs, and platform identity fields are rejected rather than user-controlled.
    """
    supplied_user_id = request.user_id or request.user or "openai-compat-user"
    supplied_session_id = request.session_id or build_compat_session_id(request)

    # Import at call time to avoid the router/main module import cycle. The app
    # has completed authentication setup before FastAPI can invoke this route.
    from app.main import _authenticated_identity, public_web_auth_configured

    if not public_web_auth_configured:
        return supplied_user_id, supplied_session_id
    if any(
        value is not None
        for value in (
            request.platform,
            request.platform_user_id,
            request.platform_group_id,
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="authenticated OpenAI requests must not include platform identity fields",
        )
    identity = await _authenticated_identity(
        user_id=supplied_user_id,
        session_id=supplied_session_id,
        session_token=hutao_session,
        csrf_token=csrf_token,
        require_csrf=True,
        authorization=authorization,
    )
    return identity.profile_id, identity.session_id


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
