from __future__ import annotations

import asyncio
import os
import shutil
import sys
import threading

if sys.platform == "win32":
    # psycopg async needs a selector-based loop (add_reader); uvicorn's default
    # ProactorEventLoop on Windows cannot support it. Set the policy before any
    # loop is created so `python -m app.main` and every programmatic start work.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path

from fastapi import Cookie, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.audio.chat_input import prepare_audio_chat_input
from app.audio.file_service import (
    AudioUploadValidationError,
    save_upload_to_temp,
    transcribe_audio_file,
    warmup_audio_pipeline,
)
from app.audio.schemas import AsrFileResponse, AudioChatFileResponse, PreparedAudioChatFileResponse
from app.audio.websocket_routes import router as audio_router
from app.auth.identity import (
    AuthenticationRequiredError,
    CsrfValidationError,
    bearer_session_token,
    resolve_web_identity,
)
from app.auth.runtime import configure_public_web_auth
from app.channels.adapters import CoreApiEventAdapter
from app.channels.contracts import ChannelEvent
from app.control.routes import router as control_router
from app.control.access import configure_control_web_runtime, control_access_middleware
from app.core.config import PROJECT_ROOT, load_settings
from app.desktop.router import create_desktop_router
from app.database_control.mysql_adapter import build_mysql_database_control_adapter
from app.database_control.persona_audit import DatabasePersonaControlAuditSink
from app.database_control.router import create_database_control_router
from app.database_control.service import DatabaseControlService
from app.expression import normalize_core_api_text, stream_core_api_text
from app.head.events import load_head_event_context
from app.head.runtime import HeadRuntime, HeadRuntimeContext
from app.knowledge.factory import build_memory_projection_provider
from app.knowledge.control import KnowledgeControlService
from app.knowledge.mysql_repository import MySQLKnowledgeRepository
from app.knowledge.router import create_knowledge_control_router
from app.openai_compat import router as openai_compat_router
from app.persona_management import (
    InMemoryPersonaManagementService,
    MySQLPersonaPersistenceStore,
    PersistentPersonaManagementService,
    create_async_persona_management_router,
    create_persona_management_router,
)
from app.persona_management.mysql_readiness import MySQLPersonaManagementReadiness
from app.persona_management.sandbox import (
    LocalSandboxPersonaService,
    SandboxPersonaError,
    SandboxPersonaNotFoundError,
)
from app.persona_management.sandbox_router import create_sandbox_persona_router
from app.schemas import (
    ChatRequest,
    ChatHistoryResponse,
    ChatHistoryMessage,
    ChatResponse,
    DeleteMemoryResponse,
    DialogueContextResponse,
    HealthResponse,
    MemoryListResponse,
    MemoryResponse,
    PublicAuthStatusResponse,
    PublicWebVoiceStatusResponse,
    WebVoiceSynthesisRequest,
)
from app.services.chat_service import ChatService
from app.services.model_client import (
    close_shared_deepseek_clients,
    get_shared_deepseek_client,
)
from app.storage.chat_repository import ChatRepository
from app.storage.repository_factory import create_chat_repository
from app.storage.v2_runtime import (
    build_database_v2_chat_repository,
    database_v2_chat_user_id,
    should_use_database_v2,
    try_handle_database_v2_platform_message,
)
from app.voice_chat.tts_service import VoiceSynthesisResult, synthesize_voice_reply
from app.voice_chat.tts_service import check_voice_provider_ready
from app.voice_chat.web_tts import (
    WebVoiceReplyBusyError,
    WebVoiceReplyNotFoundError,
    WebVoiceReplyRateLimitError,
    WebVoiceReplyStore,
)


settings = load_settings()
DESK_STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "web" / "studio"
AUTH_STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "auth"
PROFILE_STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "profile"
SHARED_STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "shared"
WEB_STATIC_ROOT = PROJECT_ROOT / "app" / "static" / "web"
SITE_STATIC_ROOT = WEB_STATIC_ROOT / "site"
CREDITS_STATIC_ROOT = WEB_STATIC_ROOT / "credits"
WEB_CURSOR_NAMES = frozenset({"pointer", "link", "text", "busy", "unavailable"})


def _resolve_web_voice_tts_output_root(relative_path: str) -> Path:
    configured_path = Path(relative_path)
    if configured_path.is_absolute():
        raise ValueError("PUBLIC_WEB_TTS_OUTPUT_DIR must be relative to the project directory")
    project_root = PROJECT_ROOT.resolve()
    output_root = (project_root / configured_path).resolve()
    if output_root == project_root or not output_root.is_relative_to(project_root):
        raise ValueError("PUBLIC_WEB_TTS_OUTPUT_DIR must stay inside the project directory")
    return output_root


memory_projection_provider = build_memory_projection_provider(settings)
app = FastAPI(title=settings.app_name)
app.mount("/site/assets", StaticFiles(directory=SITE_STATIC_ROOT / "assets"), name="public-site-assets")
app.include_router(create_desktop_router(settings))
app.include_router(audio_router)
app.include_router(openai_compat_router)
app.include_router(control_router)
database_control_repository = build_mysql_database_control_adapter(settings)
database_control_service = DatabaseControlService(database_control_repository)
app.include_router(create_database_control_router(database_control_service))
knowledge_control_service = (
    KnowledgeControlService(MySQLKnowledgeRepository(settings), database_control_repository)
    if all((settings.mysql_database, settings.mysql_user, settings.mysql_password))
    else None
)
app.include_router(create_knowledge_control_router(knowledge_control_service))
public_web_auth_runtime = configure_public_web_auth(app, settings)
public_web_auth_configured = public_web_auth_runtime.authentication_enabled
public_web_auth_service = public_web_auth_runtime.service
configure_control_web_runtime(
    enabled=public_web_auth_configured or bool(settings.control_admin_emails.strip()),
    auth_service=public_web_auth_service,
    admin_emails=settings.control_admin_emails,
    local_only=settings.control_local_only,
)
# Every control API, including feature-specific control routers registered
# above, shares the same web-admin gate when public authentication is enabled.
app.middleware("http")(control_access_middleware)
public_web_auth_uses_database_v2_profiles = public_web_auth_runtime.database_v2_profile_source
public_web_registration_configured = public_web_auth_runtime.registration_enabled
public_web_password_reset_configured = public_web_auth_runtime.password_reset_enabled
public_web_tts_configured = bool(settings.public_web_tts_enabled and public_web_auth_configured)
web_voice_reply_store = WebVoiceReplyStore(
    reply_ttl_seconds=settings.public_web_tts_reply_ttl_seconds,
    min_interval_seconds=settings.public_web_tts_min_interval_seconds,
)
web_voice_tts_output_root = _resolve_web_voice_tts_output_root(settings.public_web_tts_output_dir)
sandbox_persona_service = LocalSandboxPersonaService(Path(settings.jsonl_storage_dir))
persona_management_service = InMemoryPersonaManagementService()
app.include_router(
    create_persona_management_router(
        persona_management_service,
        database_control_repository,
    )
)
persona_runtime_projection_provider = None


@app.get("/", include_in_schema=False)
async def public_site_page() -> FileResponse:
    return FileResponse(SITE_STATIC_ROOT / "index.html")


@app.get("/credits", include_in_schema=False)
async def credits_page() -> FileResponse:
    return FileResponse(CREDITS_STATIC_ROOT / "index.html")


@app.get("/credits/style.css", include_in_schema=False)
async def credits_style() -> FileResponse:
    return FileResponse(
        CREDITS_STATIC_ROOT / "style.css",
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/credits/app.js", include_in_schema=False)
async def credits_script() -> FileResponse:
    return FileResponse(
        CREDITS_STATIC_ROOT / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/credits/data.json", include_in_schema=False)
async def credits_data() -> FileResponse:
    return FileResponse(
        CREDITS_STATIC_ROOT / "data.json",
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/desk", include_in_schema=False)
async def desk_page() -> FileResponse:
    return FileResponse(DESK_STATIC_ROOT / "index.html")


@app.get("/ui/theme.css", include_in_schema=False)
async def shared_theme_css() -> FileResponse:
    return FileResponse(
        SHARED_STATIC_ROOT / "theme.css",
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/ui/liquid-theme.css", include_in_schema=False)
async def shared_liquid_theme_css() -> FileResponse:
    return FileResponse(
        SHARED_STATIC_ROOT / "liquid-theme.css",
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/ui/ambient.js", include_in_schema=False)
async def shared_ambient_js() -> FileResponse:
    return FileResponse(
        SHARED_STATIC_ROOT / "ambient.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/ui/cursors/{cursor_name}.png", include_in_schema=False)
async def shared_web_cursor(cursor_name: str) -> FileResponse:
    if cursor_name not in WEB_CURSOR_NAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="cursor not found")
    return FileResponse(
        SHARED_STATIC_ROOT / "assets" / "cursors" / f"{cursor_name}.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/desk/app.js", include_in_schema=False)
async def desk_app_js() -> FileResponse:
    return FileResponse(
        DESK_STATIC_ROOT / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/desk/style.css", include_in_schema=False)
async def desk_style_css() -> FileResponse:
    return FileResponse(
        DESK_STATIC_ROOT / "style.css",
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/desk/manifest.webmanifest", include_in_schema=False)
async def desk_manifest() -> FileResponse:
    return FileResponse(DESK_STATIC_ROOT / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/desk/icon.svg", include_in_schema=False)
async def desk_icon() -> FileResponse:
    return FileResponse(
        DESK_STATIC_ROOT / "icon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/desk/service-worker.js", include_in_schema=False)
async def desk_service_worker() -> FileResponse:
    return FileResponse(DESK_STATIC_ROOT / "service-worker.js", media_type="application/javascript")


@app.get("/auth", include_in_schema=False)
async def auth_page() -> FileResponse:
    return FileResponse(AUTH_STATIC_ROOT / "index.html")


@app.get("/auth/app.js", include_in_schema=False)
async def auth_app_js() -> FileResponse:
    return FileResponse(AUTH_STATIC_ROOT / "app.js", media_type="application/javascript")


@app.get("/auth/style.css", include_in_schema=False)
async def auth_style_css() -> FileResponse:
    return FileResponse(AUTH_STATIC_ROOT / "style.css", media_type="text/css")


@app.get("/me", include_in_schema=False)
async def profile_page() -> FileResponse:
    return FileResponse(PROFILE_STATIC_ROOT / "index.html")


@app.get("/me/app.js", include_in_schema=False)
async def profile_app_js() -> FileResponse:
    return FileResponse(PROFILE_STATIC_ROOT / "app.js", media_type="application/javascript")


@app.get("/me/style.css", include_in_schema=False)
async def profile_style_css() -> FileResponse:
    return FileResponse(
        PROFILE_STATIC_ROOT / "style.css",
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )
persona_persistence_configured = bool(
    settings.persona_management_persistence_enabled
    and settings.database_v2_enabled
    and all((settings.mysql_database, settings.mysql_user, settings.mysql_password))
)
if persona_persistence_configured:
    persona_runtime_projection_provider = PersistentPersonaManagementService(
        MySQLPersonaPersistenceStore(settings)
    )
    app.include_router(
        create_async_persona_management_router(
            persona_runtime_projection_provider,
            database_control_repository,
            readiness_provider=MySQLPersonaManagementReadiness(settings),
            audit_sink=DatabasePersonaControlAuditSink(database_control_repository),
            enable_writes=settings.persona_management_writes_enabled,
        )
    )


def build_runtime_chat_service(*, repository=None) -> ChatService:  # type: ignore[no-untyped-def]
    kwargs = {"client": get_shared_deepseek_client(settings)}
    if repository is not None:
        kwargs["repository"] = repository
    if memory_projection_provider is not None:
        kwargs["memory_projection_provider"] = memory_projection_provider
    if persona_runtime_projection_provider is not None:
        kwargs["persona_projection_provider"] = persona_runtime_projection_provider
    service = ChatService(settings, **kwargs)
    service.sandbox_persona_projection_provider = sandbox_persona_service
    return service


def build_head_runtime(*, repository=None) -> HeadRuntime:  # type: ignore[no-untyped-def]
    return HeadRuntime(build_runtime_chat_service(repository=repository))


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        provider=settings.model_provider,
        model=settings.model_name,
        api_key_configured=bool(settings.deepseek_api_key),
    )


@app.get("/api/v1/auth/status", response_model=PublicAuthStatusResponse)
async def public_auth_status() -> PublicAuthStatusResponse:
    return PublicAuthStatusResponse(
        authentication_enabled=public_web_auth_configured,
        registration_enabled=public_web_registration_configured,
        password_reset_enabled=public_web_password_reset_configured,
    )


@app.get("/api/v1/voice/status", response_model=PublicWebVoiceStatusResponse)
async def public_web_voice_status() -> PublicWebVoiceStatusResponse:
    provider_ready = False
    if public_web_tts_configured:
        provider_ready = await run_in_threadpool(
            check_voice_provider_ready,
            provider=settings.public_web_tts_provider,
            base_url=settings.public_web_tts_base_url,
            timeout_seconds=1,
        )
    return PublicWebVoiceStatusResponse(
        enabled=public_web_tts_configured,
        max_reply_chars=settings.public_web_tts_max_reply_chars,
        provider_ready=provider_ready,
        provider=settings.public_web_tts_provider,
        base_url=settings.public_web_tts_base_url,
    )


@app.get("/api/v1/capabilities")
async def public_capabilities() -> dict[str, object]:
    """Expose the real capability boundary used by the web workspaces."""
    return {
        "chat": {"enabled": True, "provider": settings.model_provider, "model": settings.model_name},
        "memory": {
            "enabled": bool(settings.semantic_memory_enabled),
            "backend": settings.storage_backend,
        },
        "voice": {
            "enabled": public_web_tts_configured,
            "provider": settings.public_web_tts_provider,
            "status_url": "/api/v1/voice/status",
        },
        "tools": {
            "world_read": {
                "enabled": bool(settings.world_awareness_enabled),
                "label": "天气、新闻与政策只读查询",
            },
            "web_search": {
                "enabled": bool(settings.world_awareness_enabled and settings.web_search_enabled),
                "label": "通用网页搜索（实时获取，不写本地存储）",
                "provider": settings.web_search_provider,
            },
            "code_interpreter": {
                "enabled": False,
                "label": "代码解释器",
                "reason": "当前项目未提供隔离执行后端",
            },
            "computer_control": {
                "enabled": False,
                "label": "电脑控制",
                "reason": "仅保留权限策略，执行端未接入网页对话",
            },
        },
        "vision": {
            "enabled": False,
            "label": "视觉模块",
            "reason": "按项目决策已封存，不在网页中启用",
        },
    }


@app.post("/api/v1/voice/synthesize")
async def synthesize_public_web_voice(
    request: WebVoiceSynthesisRequest,
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    if not public_web_tts_configured:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="voice playback unavailable")
    identity = await _authenticated_identity(
        user_id=request.user_id,
        session_id=request.session_id,
        session_token=hutao_session,
        csrf_token=csrf_token,
        require_csrf=True,
        authorization=authorization,
    )
    try:
        reply = await web_voice_reply_store.acquire(
            request.reply_id,
            user_id=identity.profile_id,
            session_id=identity.session_id,
        )
    except WebVoiceReplyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="voice reply not found") from exc
    except WebVoiceReplyBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="voice reply is already synthesizing") from exc
    except WebVoiceReplyRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="voice request rate exceeded") from exc

    if len(reply.text) > settings.public_web_tts_max_reply_chars:
        await web_voice_reply_store.release(reply.reply_id)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="voice reply is too long")

    output_dir = web_voice_tts_output_root / reply.reply_id
    total_budget = max(1, settings.public_web_tts_total_budget_seconds)
    try:
        async with asyncio.timeout(total_budget):
            result: VoiceSynthesisResult = await run_in_threadpool(
                synthesize_voice_reply,
                user_input="网页语音播放",
                reply_text=reply.text,
                output_dir=output_dir,
                base_url=settings.public_web_tts_base_url,
                provider=settings.public_web_tts_provider,
                timeout_seconds=min(180, total_budget),
            )
        audio_path = result.send_path.resolve()
        if not audio_path.is_file() or not audio_path.is_relative_to(output_dir.resolve()):
            raise RuntimeError("web voice output escaped its request directory")
    except Exception as exc:
        _remove_web_voice_output(output_dir)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="voice synthesis unavailable") from exc
    finally:
        await web_voice_reply_store.release(reply.reply_id)

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        filename="hutao-reply.mp3",
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(_remove_web_voice_output, output_dir),
    )


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
) -> ChatResponse | JSONResponse:
    request = await _authenticated_web_request(request, hutao_session, csrf_token, authorization)
    await _validate_sandbox_persona_request(request)
    channel_event = _core_api_channel_event(request)
    assert channel_event.message is not None
    v2_response = await try_handle_database_v2_platform_message(
        settings=settings,
        platform=request.platform,
        platform_user_id=request.platform_user_id,
        platform_group_id=request.platform_group_id,
        message_text=channel_event.message.text,
    )
    if v2_response is not None:
        return await _web_voice_chat_response(
            request,
            v2_response.model_copy(update={"text": normalize_core_api_text(v2_response.text)}),
        )
    use_v2_chat_storage = _should_use_database_v2_chat_storage(request)
    chat_user_id = (
        database_v2_chat_user_id(
            platform=request.platform,
            platform_user_id=request.platform_user_id,
            fallback_user_id=request.user_id,
        )
        if use_v2_chat_storage
        else request.user_id
    )
    runtime = (
        build_head_runtime(repository=build_database_v2_chat_repository(settings))
        if use_v2_chat_storage
        else build_head_runtime()
    )
    context = _head_runtime_context(request, chat_user_id)
    if request.input_source == "audio":
        response = await _reply_with_audio_budget(runtime, channel_event, context)
    else:
        response = await runtime.handle(channel_event, context)
    return await _web_voice_chat_response(
        request,
        response.model_copy(update={"text": normalize_core_api_text(response.text)}),
    )


async def _web_voice_chat_response(
    request: ChatRequest,
    response: ChatResponse,
) -> ChatResponse | JSONResponse:
    if not public_web_tts_configured or not response.text.strip():
        return response
    reply_id = await web_voice_reply_store.remember(
        user_id=request.user_id,
        session_id=request.session_id,
        text=response.text,
    )
    return JSONResponse(
        content=response.model_dump(mode="json"),
        headers={"X-Hutao-Reply-Id": reply_id},
    )


@app.post("/api/v1/chat/stream")
async def chat_stream(
    request: ChatRequest,
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    request = await _authenticated_web_request(request, hutao_session, csrf_token, authorization)
    await _validate_sandbox_persona_request(request)
    channel_event = _core_api_channel_event(request)
    assert channel_event.message is not None
    v2_response = await try_handle_database_v2_platform_message(
        settings=settings,
        platform=request.platform,
        platform_user_id=request.platform_user_id,
        platform_group_id=request.platform_group_id,
        message_text=channel_event.message.text,
    )
    if v2_response is not None:
        async def stream_v2_response():
            yield normalize_core_api_text(v2_response.text)

        return _web_voice_streaming_response(
            request,
            _limit_audio_stream_if_needed(request, stream_v2_response()),
        )
    use_v2_chat_storage = _should_use_database_v2_chat_storage(request)
    chat_user_id = (
        database_v2_chat_user_id(
            platform=request.platform,
            platform_user_id=request.platform_user_id,
            fallback_user_id=request.user_id,
        )
        if use_v2_chat_storage
        else request.user_id
    )
    runtime = (
        build_head_runtime(repository=build_database_v2_chat_repository(settings))
        if use_v2_chat_storage
        else build_head_runtime()
    )
    return _web_voice_streaming_response(
        request,
        _limit_audio_stream_if_needed(
            request,
            stream_core_api_text(runtime.stream(channel_event, _head_runtime_context(request, chat_user_id))),
        ),
    )


def _limit_audio_stream_if_needed(
    request: ChatRequest,
    chunks: AsyncIterable[str | bytes],
) -> AsyncIterable[str | bytes]:
    if request.input_source != "audio":
        return chunks
    return limit_audio_stream_to_realtime_budget(
        chunks,
        timeout_seconds=settings.voice_chat_reply_timeout_seconds,
    )


async def limit_audio_stream_to_realtime_budget(
    chunks: AsyncIterable[str | bytes],
    *,
    timeout_seconds: float,
) -> AsyncIterator[str | bytes]:
    try:
        async with asyncio.timeout(timeout_seconds):
            async for chunk in chunks:
                yield chunk
    except TimeoutError:
        yield "\u8fd9\u6b21\u56de\u590d\u8017\u65f6\u8fc7\u957f\uff0c\u8bf7\u70b9\u51fb\u91cd\u8bd5\u3002"


async def _reply_with_audio_budget(runtime, channel_event, context) -> ChatResponse:
    """Bound a non-streaming audio chat reply to the realtime voice budget."""
    try:
        async with asyncio.timeout(settings.voice_chat_reply_timeout_seconds):
            return await runtime.handle(channel_event, context)
    except TimeoutError:
        return ChatResponse(
            text="\u8fd9\u6b21\u56de\u590d\u8017\u65f6\u8fc7\u957f\uff0c\u8bf7\u70b9\u51fb\u91cd\u8bd5\u3002",
            provider="local",
            model="audio-chat-timeout",
            used_live_api=False,
            fallback_used=True,
            error="audio chat reply exceeded the realtime budget",
        )


def _web_voice_streaming_response(
    request: ChatRequest,
    chunks: AsyncIterable[str | bytes],
) -> StreamingResponse:
    if not public_web_tts_configured:
        return StreamingResponse(chunks, media_type="text/plain; charset=utf-8")
    reply_id = web_voice_reply_store.new_reply_id()
    return StreamingResponse(
        _remember_completed_web_voice_reply(request, reply_id, chunks),
        media_type="text/plain; charset=utf-8",
        headers={"X-Hutao-Reply-Id": reply_id},
    )


async def _remember_completed_web_voice_reply(
    request: ChatRequest,
    reply_id: str,
    chunks: AsyncIterable[str | bytes],
) -> AsyncIterator[str | bytes]:
    reply_bytes = bytearray()
    completed = False
    try:
        async for chunk in chunks:
            reply_bytes.extend(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            yield chunk
        completed = True
    finally:
        try:
            reply_text = bytes(reply_bytes).decode("utf-8")
        except UnicodeDecodeError:
            return
        if completed and reply_text.strip():
            await web_voice_reply_store.remember(
                reply_id=reply_id,
                user_id=request.user_id,
                session_id=request.session_id,
                text=reply_text,
            )


def _remove_web_voice_output(output_dir: Path) -> None:
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        output_dir.parent.rmdir()
    except OSError:
        pass


def _core_api_channel_event(request: ChatRequest) -> ChannelEvent:
    return CoreApiEventAdapter().adapt(request)


def _web_chat_uses_postgres() -> bool:
    return settings.storage_backend.strip().lower() in {"postgres", "postgresql"}


def _should_use_database_v2_chat_storage(request: ChatRequest) -> bool:
    # Dual-track: PostgreSQL owns web chat history/memories when selected as the
    # storage backend; Database V2 (MySQL) keeps the identity/profile layer only.
    if _web_chat_uses_postgres():
        return False
    return should_use_database_v2(
        settings,
        platform=request.platform,
        platform_user_id=request.platform_user_id,
        trusted_core_profile=(
            public_web_auth_configured
            and public_web_auth_uses_database_v2_profiles
            and request.platform is None
        ),
    )


def _authenticated_profile_repository() -> ChatRepository:
    if _web_chat_uses_postgres():
        return create_chat_repository(settings)
    if public_web_auth_configured and public_web_auth_uses_database_v2_profiles:
        return build_database_v2_chat_repository(settings)
    return create_chat_repository(settings)


async def _authenticated_web_request(
    request: ChatRequest,
    session_token: str | None,
    csrf_token: str | None = None,
    authorization: str | None = None,
) -> ChatRequest:
    if public_web_auth_configured and any(
        value is not None for value in (request.platform, request.platform_user_id, request.platform_group_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="public web requests must not include platform identity fields",
        )
    identity = await _authenticated_identity(
        user_id=request.user_id,
        session_id=request.session_id,
        session_token=session_token,
        csrf_token=csrf_token,
        require_csrf=True,
        authorization=authorization,
    )
    return request.model_copy(
        update={"user_id": identity.profile_id, "session_id": identity.session_id}
    )


def _head_runtime_context(request: ChatRequest, subject_id: str) -> HeadRuntimeContext:
    return HeadRuntimeContext(
        subject_id=subject_id,
        session_id=request.session_id,
        input_source=request.input_source,
        input_quality_passed=request.input_quality_passed,
        input_quality_reasons=tuple(request.input_quality_reasons),
        input_emotion=request.input_emotion,
        input_emotion_source=request.input_emotion_source,
        input_emotion_confidence=request.input_emotion_confidence,
        response_style_instruction=request.response_style_instruction,
        sandbox_persona_id=request.persona_id,
    )


async def _validate_sandbox_persona_request(request: ChatRequest) -> None:
    if not request.persona_id:
        return
    if request.platform is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sandbox personas are only available to the Web sandbox",
        )
    try:
        await sandbox_persona_service.get_runtime_projection(
            request.persona_id,
            owner_id=request.user_id,
        )
    except SandboxPersonaNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sandbox persona not found") from exc
    except SandboxPersonaError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="sandbox persona storage unavailable",
        ) from exc


@app.post("/api/v1/audio/transcribe/file", response_model=AsrFileResponse)
async def transcribe_audio_file_endpoint(
    file: UploadFile = File(...),
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
) -> AsrFileResponse:
    await _authenticated_identity(
        user_id="local-audio-user",
        session_id="local-audio-transcription",
        session_token=hutao_session,
        csrf_token=csrf_token,
        require_csrf=True,
        authorization=authorization,
    )
    audio_path = await _save_audio_upload(file)
    try:
        return await run_in_threadpool(transcribe_audio_file, audio_path)
    finally:
        audio_path.unlink(missing_ok=True)


@app.post("/api/v1/audio/chat/prepare/file", response_model=PreparedAudioChatFileResponse)
async def prepare_audio_chat_file_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(default="default"),
    user_id: str = Form(default="default-user"),
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
) -> PreparedAudioChatFileResponse:
    await _authenticated_identity(
        user_id=user_id,
        session_id=session_id,
        session_token=hutao_session,
        csrf_token=csrf_token,
        require_csrf=True,
        authorization=authorization,
    )
    audio_path = await _save_audio_upload(file)
    try:
        transcription = await run_in_threadpool(
            transcribe_audio_file,
            audio_path,
            include_emotion=False,
        )
        prepared_audio_input = prepare_audio_chat_input(transcription)
        return PreparedAudioChatFileResponse(
            transcript_text=transcription.text,
            chat_input_text=prepared_audio_input.text,
            chat_bypassed_due_to_asr_quality=prepared_audio_input.should_clarify,
            chat_bypass_reasons=prepared_audio_input.clarify_reasons,
            clarification_reply=(
                prepared_audio_input.clarification_reply
                if prepared_audio_input.should_clarify
                else None
            ),
            asr=transcription,
        )
    finally:
        audio_path.unlink(missing_ok=True)


@app.post("/api/v1/audio/chat/file", response_model=AudioChatFileResponse)
async def audio_chat_file_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(default="default"),
    user_id: str = Form(default="default-user"),
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
) -> AudioChatFileResponse:
    identity = await _authenticated_identity(
        user_id=user_id,
        session_id=session_id,
        session_token=hutao_session,
        csrf_token=csrf_token,
        require_csrf=True,
        authorization=authorization,
    )
    session_id = identity.session_id
    user_id = identity.profile_id
    audio_path = await _save_audio_upload(file)
    try:
        transcription = await run_in_threadpool(transcribe_audio_file, audio_path)
        prepared_audio_input = prepare_audio_chat_input(transcription)
        if prepared_audio_input.should_clarify:
            chat_response = ChatResponse(
                text=prepared_audio_input.clarification_reply,
                provider="local",
                model="audio-chat-quality-gate",
                used_live_api=False,
                fallback_used=True,
                error="ASR quality gate requested clarification: "
                + ",".join(prepared_audio_input.clarify_reasons),
            )
        else:
            audio_event = CoreApiEventAdapter().adapt(
                {
                    "user_input": prepared_audio_input.text,
                    "session_id": session_id,
                    "user_id": user_id,
                }
            )
            runtime = (
                build_head_runtime(repository=build_database_v2_chat_repository(settings))
                if public_web_auth_configured
                and public_web_auth_uses_database_v2_profiles
                and not _web_chat_uses_postgres()
                else build_head_runtime()
            )
            chat_response = await _reply_with_audio_budget(
                runtime,
                audio_event,
                HeadRuntimeContext(
                    subject_id=user_id,
                    session_id=session_id,
                    input_source="audio",
                    input_quality_passed=transcription.quality_passed,
                    input_quality_reasons=tuple(transcription.quality_reasons),
                    input_emotion=transcription.emotion,
                    input_emotion_source=transcription.emotion_source,
                    input_emotion_confidence=transcription.emotion_confidence,
                ),
            )
        return AudioChatFileResponse(
            transcript_text=transcription.text,
            chat_input_text=prepared_audio_input.text,
            chat_bypassed_due_to_asr_quality=prepared_audio_input.should_clarify,
            chat_bypass_reasons=prepared_audio_input.clarify_reasons,
            reply_text=chat_response.text,
            asr=transcription,
            chat=chat_response,
        )
    finally:
        audio_path.unlink(missing_ok=True)


async def _save_audio_upload(file: UploadFile) -> Path:
    try:
        return await save_upload_to_temp(
            file,
            max_bytes=settings.audio_upload_max_bytes,
            allowed_extensions=settings.audio_upload_allowed_extensions,
            allowed_content_types=settings.audio_upload_allowed_content_types,
        )
    except AudioUploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/v1/memories", response_model=MemoryListResponse)
async def list_memories(
    user_id: str = "default-user",
    limit: int = 20,
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    authorization: str | None = Header(default=None),
) -> MemoryListResponse:
    identity = await _authenticated_memory_identity(user_id, hutao_session, authorization=authorization)
    repository = _authenticated_profile_repository()
    records = await repository.list_memories(
        user_id=identity.profile_id,
        limit=min(max(limit, 1), 100),
    )

    return MemoryListResponse(
        memories=[
            MemoryResponse(
                id=record.id,
                user_id=record.user_id,
                session_id=record.session_id,
                memory_type=record.memory_type,
                content=record.content,
                confidence=record.confidence,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in records
        ]
    )


@app.get("/api/v1/chat/history", response_model=ChatHistoryResponse)
async def chat_history(
    session_id: str = "default",
    user_id: str = "default-user",
    limit: int = 80,
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    authorization: str | None = Header(default=None),
) -> ChatHistoryResponse:
    identity = await _authenticated_identity(
        user_id=user_id,
        session_id=session_id,
        session_token=hutao_session,
        authorization=authorization,
        csrf_token=None,
        require_csrf=False,
    )
    records = await _authenticated_profile_repository().list_recent_messages(
        session_id=identity.session_id,
        limit=min(max(limit, 1), 100),
    )
    owned_records = [record for record in records if record.user_id == identity.profile_id]
    return ChatHistoryResponse(
        session_id=identity.session_id,
        messages=[
            ChatHistoryMessage(
                id=record.id,
                role=record.role,
                content=record.content,
                created_at=record.created_at,
            )
            for record in owned_records
        ],
    )


@app.delete("/api/v1/memories/{memory_id}", response_model=DeleteMemoryResponse)
async def delete_memory(
    memory_id: str,
    user_id: str = "default-user",
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authorization: str | None = Header(default=None),
) -> DeleteMemoryResponse:
    identity = await _authenticated_memory_identity(
        user_id,
        hutao_session,
        csrf_token=csrf_token,
        require_csrf=True,
        authorization=authorization,
    )
    repository = _authenticated_profile_repository()
    return DeleteMemoryResponse(
        deleted=await repository.delete_memory(user_id=identity.profile_id, memory_id=memory_id)
    )


@app.get("/api/v1/dialogue-context", response_model=DialogueContextResponse)
async def dialogue_context(
    user_id: str = "default-user",
    hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
    authorization: str | None = Header(default=None),
) -> DialogueContextResponse:
    identity = await _authenticated_memory_identity(user_id, hutao_session, authorization=authorization)
    context = await load_head_event_context(
        _authenticated_profile_repository(),
        user_id=identity.profile_id,
    )
    active_task = _user_visible_head_text(context.active_task)
    pending_question = _user_visible_head_text(context.pending_question)
    status_value = (
        "waiting_for_user"
        if pending_question is not None
        else "tracking_task"
        if active_task is not None
        else "ready"
    )
    return DialogueContextResponse(
        status=status_value,
        active_task=active_task,
        pending_question=pending_question,
    )


def _user_visible_head_text(value: str) -> str | None:
    normalized = " ".join(value.split())
    if not normalized or normalized == "none" or normalized.startswith(("{", "[")):
        return None
    return normalized[:240]


async def _authenticated_memory_identity(
    user_id: str,
    session_token: str | None,
    *,
    csrf_token: str | None = None,
    require_csrf: bool = False,
    authorization: str | None = None,
):
    return await _authenticated_identity(
        user_id=user_id,
        session_id="memory-read",
        session_token=session_token,
        csrf_token=csrf_token,
        require_csrf=require_csrf,
        authorization=authorization,
    )


async def _authenticated_identity(
    *,
    user_id: str,
    session_id: str,
    session_token: str | None,
    csrf_token: str | None,
    require_csrf: bool,
    authorization: str | None = None,
):
    try:
        return await resolve_web_identity(
            auth_service=public_web_auth_service,
            public_auth_enabled=public_web_auth_configured,
            session_token=bearer_session_token(authorization) or session_token,
            csrf_token=csrf_token,
            require_csrf=require_csrf,
            supplied_user_id=user_id,
            supplied_session_id=session_id,
        )
    except CsrfValidationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf validation failed") from exc
    except AuthenticationRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required") from exc


async def _resolve_sandbox_persona_owner(
    user_id: str,
    session_token: str | None,
    csrf_token: str | None,
    authorization: str | None,
    require_csrf: bool,
) -> str:
    identity = await _authenticated_identity(
        user_id=user_id,
        session_id="sandbox-personas",
        session_token=session_token,
        csrf_token=csrf_token,
        require_csrf=require_csrf,
        authorization=authorization,
    )
    return identity.profile_id


app.include_router(
    create_sandbox_persona_router(
        sandbox_persona_service,
        _resolve_sandbox_persona_owner,
    )
)


@app.on_event("startup")
async def _warmup_audio_on_startup() -> None:
    if settings.audio_warmup_enabled:
        threading.Thread(
            target=warmup_audio_pipeline,
            name="audio-warmup",
            daemon=True,
        ).start()


@app.on_event("shutdown")
async def _close_shared_model_clients() -> None:
    await close_shared_deepseek_clients()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        loop="app.loop_factory:selector_loop_factory",
    )
