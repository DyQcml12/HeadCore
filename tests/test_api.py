from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx

import app.main as main
from app.audio.schemas import AsrFileResponse
from app.channels.contracts import ChannelEvent
from app.core.config import load_settings
from app.main import app
from app.main import _core_api_channel_event
from app.schemas import ChatRequest
from app.schemas import ChatResponse
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.storage.chat_repository import JsonlChatRepository
from app.storage.repository_factory import create_chat_repository


class FakeSuccessClient:
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        return "收到，我先陪你从最小的那一步开始。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):
        for chunk in ["收到，", "先从小步来。"]:
            yield chunk


class RecordingChatService(ChatService):
    last_call: dict[str, object] = {}

    async def reply(self, user_input: str, **kwargs) -> object:
        type(self).last_call = {"user_input": user_input, **kwargs}
        return await super().reply(user_input, **kwargs)


class FakeFileAsrEngine:
    provider = "fake-asr"
    model = "fake-file-model"

    def transcribe_file(self, audio_path: Path) -> str:
        return "欢迎大家来体验语音识别模型。"


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def get_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/health")


async def request_app(method: str, url: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, url, **kwargs)


def test_health_reports_runtime_shape() -> None:
    response = asyncio.run(get_health())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "deepseek"
    assert "api_key_configured" in body


def test_public_capabilities_report_only_connected_tools(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", replace(main.settings, world_awareness_enabled=True))
    monkeypatch.setattr(main, "public_web_tts_configured", False)

    response = asyncio.run(request_app("GET", "/api/v1/capabilities"))

    assert response.status_code == 200
    body = response.json()
    assert body["chat"]["enabled"] is True
    assert body["memory"]["enabled"] is bool(main.settings.semantic_memory_enabled)
    assert body["tools"]["world_read"]["enabled"] is True
    assert body["tools"]["web_search"]["enabled"] is False
    assert body["tools"]["code_interpreter"]["enabled"] is False
    assert body["tools"]["computer_control"]["enabled"] is False
    assert body["vision"]["enabled"] is False
    assert body["voice"]["enabled"] is False


def test_chat_history_returns_only_the_local_owner_messages(monkeypatch, tmp_path: Path) -> None:
    repository = JsonlChatRepository(tmp_path)
    asyncio.run(repository.ensure_session(user_id="local-owner", client_session_id="desk-session"))
    asyncio.run(
        repository.save_message(
            session_id="session-record",
            user_id="local-owner",
            role="user",
            content="第一条消息",
        )
    )
    asyncio.run(
        repository.save_message(
            session_id="session-record",
            user_id="other-owner",
            role="assistant",
            content="不应返回",
        )
    )
    monkeypatch.setattr(main, "public_web_auth_configured", False)
    monkeypatch.setattr(main, "_authenticated_profile_repository", lambda: repository)

    response = asyncio.run(
        request_app(
            "GET",
            "/api/v1/chat/history?session_id=session-record&user_id=local-owner",
        )
    )

    assert response.status_code == 200
    assert response.json()["messages"] == [
        {
            "id": response.json()["messages"][0]["id"],
            "role": "user",
            "content": "第一条消息",
            "created_at": response.json()["messages"][0]["created_at"],
        }
    ]


def test_public_web_chat_identity_comes_from_session_not_request_body(monkeypatch) -> None:
    from app.auth.service import StoredSession
    from app.main import _authenticated_web_request

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **_kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            return StoredSession(
                id="server-session",
                user_id="web-user",
                profile_id="profile-from-session",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())

    request = asyncio.run(
        _authenticated_web_request(
            ChatRequest(
                user_input="身份边界测试",
                user_id="attacker-profile",
                session_id="attacker-session",
            ),
            "valid-session",
        )
    )

    assert request.user_id == "profile-from-session"
    assert request.session_id == "server-session"


def test_authenticated_mysql_profile_uses_v2_chat_storage(monkeypatch) -> None:
    from app.auth.service import StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            assert kwargs == {"csrf_token": "csrf-value", "require_csrf": True}
            return StoredSession(
                id="server-session",
                user_id="web-user",
                profile_id="profile-from-session",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    class RecordingRuntime:
        repository = None
        context = None

        async def handle(self, _event, context):
            type(self).context = context
            return ChatResponse(text="收到", provider="test", model="test", used_live_api=False)

    fake_repository = object()

    async def no_platform_command(**_kwargs):
        return None

    def build_runtime(*, repository=None):
        RecordingRuntime.repository = repository
        return RecordingRuntime()

    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_uses_database_v2_profiles", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())
    monkeypatch.setattr("app.main.settings", replace(main.settings, database_v2_enabled=True))
    monkeypatch.setattr("app.main.try_handle_database_v2_platform_message", no_platform_command)
    monkeypatch.setattr("app.main.build_database_v2_chat_repository", lambda _settings: fake_repository)
    monkeypatch.setattr("app.main.build_head_runtime", build_runtime)

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            headers={"Cookie": "hutao_session=valid-session", "X-CSRF-Token": "csrf-value"},
            json={"user_input": "身份边界", "user_id": "attacker-profile", "session_id": "attacker-session"},
        )
    )

    assert response.status_code == 200
    assert RecordingRuntime.repository is fake_repository
    assert RecordingRuntime.context.subject_id == "profile-from-session"
    assert RecordingRuntime.context.session_id == "server-session"


def test_authenticated_mysql_profile_uses_v2_memory_repository(monkeypatch) -> None:
    from app.auth.service import StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **_kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            return StoredSession(
                id="server-session",
                user_id="web-user",
                profile_id="profile-from-session",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    class RecordingRepository:
        user_ids: list[str] = []

        async def list_memories(self, *, user_id: str, limit: int):
            type(self).user_ids.append(user_id)
            assert limit == 20
            return []

    repository = RecordingRepository()
    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_uses_database_v2_profiles", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())
    monkeypatch.setattr("app.main.build_database_v2_chat_repository", lambda _settings: repository)

    response = asyncio.run(
        request_app(
            "GET",
            "/api/v1/memories?user_id=attacker-profile",
            headers={"Cookie": "hutao_session=valid-session"},
        )
    )

    assert response.status_code == 200
    assert response.json() == {"memories": []}
    assert RecordingRepository.user_ids == ["profile-from-session"]


def test_public_web_chat_rejects_write_without_csrf_token(monkeypatch) -> None:
    from app.auth.service import AuthenticationError, StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            if kwargs.get("require_csrf") is not True or not kwargs.get("csrf_token"):
                raise AuthenticationError("csrf validation failed")
            return StoredSession(
                id="server-session",
                user_id="web-user",
                profile_id="profile-from-session",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            headers={"Cookie": "hutao_session=valid-session"},
            json={"user_input": "不应执行的跨站写请求", "user_id": "attacker-profile"},
        )
    )

    assert response.status_code == 403


def test_public_chat_uses_mini_program_bearer_identity_not_request_values(monkeypatch) -> None:
    from app.auth.service import StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            assert session_token == "mini-session-token"
            assert kwargs == {"csrf_token": "csrf-mini", "require_csrf": True}
            return StoredSession(
                id="mini-server-session",
                user_id="web-user",
                profile_id="profile-from-bearer",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    class RecordingRuntime:
        context = None

        async def handle(self, _event, context):
            type(self).context = context
            return ChatResponse(text="收到", provider="test", model="test", used_live_api=False)

    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())
    monkeypatch.setattr("app.main.build_head_runtime", lambda: RecordingRuntime())

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            headers={"Authorization": "Bearer mini-session-token", "X-CSRF-Token": "csrf-mini"},
            json={"user_input": "身份边界", "user_id": "attacker-profile", "session_id": "attacker-session"},
        )
    )

    assert response.status_code == 200
    assert RecordingRuntime.context.subject_id == "profile-from-bearer"
    assert RecordingRuntime.context.session_id == "mini-server-session"


def test_public_web_memory_delete_rejects_write_without_csrf_token(monkeypatch) -> None:
    from app.auth.service import AuthenticationError, StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            if kwargs.get("require_csrf") is not True or not kwargs.get("csrf_token"):
                raise AuthenticationError("csrf validation failed")
            raise AssertionError("memory repository must not be reached")

    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())

    response = asyncio.run(
        request_app(
            "DELETE",
            "/api/v1/memories/memory-1?user_id=attacker-profile",
            headers={"Cookie": "hutao_session=valid-session"},
        )
    )

    assert response.status_code == 403


def test_public_web_audio_chat_uses_server_identity_not_form_values(monkeypatch) -> None:
    from app.auth.service import StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            assert kwargs == {"csrf_token": "csrf-value", "require_csrf": True}
            return StoredSession(
                id="server-session",
                user_id="web-user",
                profile_id="profile-from-session",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    class RecordingRuntime:
        context = None

        async def handle(self, _event, context):
            type(self).context = context
            return ChatResponse(text="收到", provider="test", model="test", used_live_api=False)

    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())
    monkeypatch.setattr(
        "app.main.transcribe_audio_file",
        lambda audio_path: AsrFileResponse(
            text="身份边界语音测试。",
            provider="fake-asr",
            model="fake-file-model",
            audio_path=str(audio_path),
            latency_ms=1.0,
        ),
    )
    monkeypatch.setattr("app.main.build_head_runtime", lambda: RecordingRuntime())

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/chat/file",
            headers={"Cookie": "hutao_session=valid-session", "X-CSRF-Token": "csrf-value"},
            data={"session_id": "attacker-session", "user_id": "attacker-profile"},
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    assert response.status_code == 200
    assert RecordingRuntime.context.subject_id == "profile-from-session"
    assert RecordingRuntime.context.session_id == "server-session"


def test_authenticated_mysql_audio_chat_uses_v2_repository(monkeypatch) -> None:
    from app.auth.service import StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            assert kwargs == {"csrf_token": "csrf-value", "require_csrf": True}
            return StoredSession(
                id="server-session",
                user_id="web-user",
                profile_id="profile-from-session",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    class RecordingRuntime:
        repository = None
        context = None

        async def handle(self, _event, context):
            type(self).context = context
            return ChatResponse(text="收到", provider="test", model="test", used_live_api=False)

    fake_repository = object()

    def build_runtime(*, repository=None):
        RecordingRuntime.repository = repository
        return RecordingRuntime()

    monkeypatch.setattr("app.main.public_web_auth_configured", True)
    monkeypatch.setattr("app.main.public_web_auth_uses_database_v2_profiles", True)
    monkeypatch.setattr("app.main.public_web_auth_service", FakePublicAuthService())
    monkeypatch.setattr("app.main.build_database_v2_chat_repository", lambda _settings: fake_repository)
    monkeypatch.setattr("app.main.build_head_runtime", build_runtime)
    monkeypatch.setattr(
        "app.main.transcribe_audio_file",
        lambda audio_path: AsrFileResponse(
            text="语音身份边界测试。",
            provider="fake-asr",
            model="fake-file-model",
            audio_path=str(audio_path),
            latency_ms=1.0,
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/chat/file",
            headers={"Cookie": "hutao_session=valid-session", "X-CSRF-Token": "csrf-value"},
            data={"session_id": "attacker-session", "user_id": "attacker-profile"},
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    assert response.status_code == 200
    assert RecordingRuntime.repository is fake_repository
    assert RecordingRuntime.context.subject_id == "profile-from-session"
    assert RecordingRuntime.context.session_id == "server-session"


def test_persona_management_routes_are_registered_read_only() -> None:
    paths = app.openapi()["paths"]
    persona_paths = {
        path: methods
        for path, methods in paths.items()
        if path.startswith("/api/control/personas")
    }

    assert set(persona_paths) == {
        "/api/control/personas/status",
        "/api/control/personas/{profile_id}/versions",
        "/api/control/personas/{profile_id}/releases",
        "/api/control/personas/versions/{version_id}",
        "/api/control/personas/bindings/all",
        "/api/control/personas/{profile_id}/runtime-projection",
    }
    assert all(set(methods) == {"get"} for methods in persona_paths.values())


def test_persona_management_status_requires_actor_headers() -> None:
    response = asyncio.run(request_app("GET", "/api/control/personas/status"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_persona_management_status_reports_non_durable_backend_for_admin(monkeypatch) -> None:
    from app.database_control.contracts import (
        DatabaseActor,
        DatabasePermissions,
        SourceAccount,
    )

    async def resolve_admin(identity):
        return DatabaseActor(
            profile_id="admin-profile",
            relationship_type="admin_partner",
            permissions=DatabasePermissions(read_admin=True, mutate_admin=True),
            source_account=SourceAccount(id="account", platform="qq", status="active"),
        )

    monkeypatch.setattr("app.main.database_control_repository.resolve_actor", resolve_admin)
    response = asyncio.run(
        request_app(
            "GET",
            "/api/control/personas/status",
            headers={
                "X-Hutao-Actor-Platform": "qq",
                "X-Hutao-Actor-User-Id": "10001",
            },
        )
    )

    assert response.status_code == 200
    assert response.json() == {
        "storage_backend": "memory",
        "durable": False,
        "write_ready": False,
        "draft_count": 0,
        "version_count": 0,
        "release_count": 0,
        "binding_count": 0,
        "active_profiles": [],
    }


def test_core_api_chat_request_builds_unified_channel_event() -> None:
    event = _core_api_channel_event(
        ChatRequest(
            user_input="统一事件测试",
            session_id="session-channel",
            user_id="internal-user",
            platform="qq",
            platform_user_id="10001",
            platform_group_id="20002",
        )
    )

    assert isinstance(event, ChannelEvent)
    assert event.platform == "core_api"
    assert event.identity.user_id == "10001"
    assert event.thread.thread_type == "group"
    assert event.thread.thread_id == "20002"
    assert event.message is not None
    assert event.message.text == "统一事件测试"
    assert event.metadata["source_platform"] == "qq"


def test_chat_and_stream_runtime_both_adapt_core_api_event(monkeypatch) -> None:
    from app.channels.adapters import CoreApiEventAdapter

    calls: list[str] = []
    original_adapt = CoreApiEventAdapter.adapt

    def recording_adapt(self, request, **kwargs):
        calls.append(request.user_input)
        return original_adapt(self, request, **kwargs)

    async def fake_v2_handler(**kwargs):
        return ChatResponse(
            text="handled",
            provider="local",
            model="fake-v2",
            used_live_api=False,
        )

    monkeypatch.setattr(CoreApiEventAdapter, "adapt", recording_adapt)
    monkeypatch.setattr("app.main.try_handle_database_v2_platform_message", fake_v2_handler)

    chat_response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            json={"user_input": "chat-event", "session_id": "s1", "user_id": "u1"},
        )
    )
    stream_response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat/stream",
            json={"user_input": "stream-event", "session_id": "s2", "user_id": "u2"},
        )
    )

    assert chat_response.status_code == 200
    assert stream_response.status_code == 200
    assert calls == ["chat-event", "stream-event"]


def test_memory_management_api_lists_and_deletes_user_memories(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "api-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())

    repository = create_chat_repository(load_settings())
    own_memory = asyncio.run(
        repository.save_memory(
            user_id="u-api",
            session_id="s1",
            memory_type="conversation_preference",
            content="回复风格=短句",
            confidence=0.9,
        )
    )
    other_memory = asyncio.run(
        repository.save_memory(
            user_id="other-user",
            session_id="s2",
            memory_type="user_alias",
            content="称呼=阿明",
            confidence=0.9,
        )
    )

    list_response = asyncio.run(request_app("GET", "/api/v1/memories?user_id=u-api"))
    delete_wrong_owner = asyncio.run(
        request_app("DELETE", f"/api/v1/memories/{other_memory.id}?user_id=u-api")
    )
    delete_own = asyncio.run(
        request_app("DELETE", f"/api/v1/memories/{own_memory.id}?user_id=u-api")
    )
    list_after_delete = asyncio.run(request_app("GET", "/api/v1/memories?user_id=u-api"))

    assert list_response.status_code == 200
    body = list_response.json()
    assert [memory["id"] for memory in body["memories"]] == [own_memory.id]
    assert body["memories"][0]["content"] == "回复风格=短句"
    assert delete_wrong_owner.json() == {"deleted": False}
    assert delete_own.json() == {"deleted": True}
    assert list_after_delete.json() == {"memories": []}


def test_dialogue_context_projects_only_user_safe_head_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "dialogue-context-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())

    repository = create_chat_repository(load_settings())
    asyncio.run(
        repository.save_memory(
            user_id="u-dialogue-context",
            session_id="s1",
            memory_type="head_task",
            content="整理网页与账号设置的开发顺序",
            confidence=0.8,
        )
    )
    asyncio.run(
        repository.save_memory(
            user_id="u-dialogue-context",
            session_id="s1",
            memory_type="head_pending_question",
            content="确认是否先开放通用 OpenAI-compatible Provider",
            confidence=0.8,
        )
    )
    asyncio.run(
        repository.save_memory(
            user_id="u-dialogue-context",
            session_id="s1",
            memory_type="head_last_action",
            content='{"internal_reasoning":"must not reach the browser"}',
            confidence=1.0,
        )
    )
    asyncio.run(
        repository.save_memory(
            user_id="u-dialogue-context",
            session_id="s1",
            memory_type="head_world_model",
            content='{"internal_world_graph":"must not reach the browser"}',
            confidence=1.0,
        )
    )

    response = asyncio.run(
        request_app("GET", "/api/v1/dialogue-context?user_id=u-dialogue-context")
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "waiting_for_user",
        "active_task": "整理网页与账号设置的开发顺序",
        "pending_question": "确认是否先开放通用 OpenAI-compatible Provider",
    }
    assert "internal_reasoning" not in response.text
    assert "internal_world_graph" not in response.text


def test_streaming_chat_api_returns_text_and_persists(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "stream-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())
    monkeypatch.setattr("app.main.ChatService", lambda settings, **kwargs: ChatService(
        settings,
        client=FakeSuccessClient(),
        repository=create_chat_repository(settings),
        audit_logger=ModelInvocationAuditLogger(tmp_path / "audit.jsonl"),
    ))

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat/stream",
            json={"user_input": "少说点。", "session_id": "s1", "user_id": "u1"},
        )
    )

    messages = read_jsonl(tmp_path / "stream-storage" / "messages.jsonl")
    assert response.status_code == 200
    assert response.text == "收到，先从小步来。"
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == response.text


def test_chat_api_uses_database_v2_prehandler_when_it_returns_response(monkeypatch) -> None:
    RecordingChatService.last_call = {}

    async def fake_v2_handler(**kwargs):
        return ChatResponse(
            text="relationship command handled",
            provider="local",
            model="database-v2-platform-command",
            used_live_api=False,
            fallback_used=True,
            error="blocked",
        )

    monkeypatch.setattr("app.main.try_handle_database_v2_platform_message", fake_v2_handler)
    monkeypatch.setattr("app.main.ChatService", lambda settings, **kwargs: RecordingChatService(settings))

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            json={
                "user_input": "小何 拉黑 qq 123456",
                "session_id": "s-v2",
                "user_id": "u-v2",
                "platform": "qq",
                "platform_user_id": "10001",
            },
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["text"] == "relationship command handled"
    assert body["model"] == "database-v2-platform-command"
    assert RecordingChatService.last_call == {}


def test_chat_api_falls_back_to_chat_service_when_v2_returns_none(monkeypatch, tmp_path: Path) -> None:
    RecordingChatService.last_call = {}
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "v2-fallback-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())

    async def fake_v2_handler(**kwargs):
        return None

    monkeypatch.setattr("app.main.try_handle_database_v2_platform_message", fake_v2_handler)
    monkeypatch.setattr(
        "app.main.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            json={"user_input": "正常聊天", "session_id": "s-v2-none", "user_id": "u-v2-none"},
        )
    )

    assert response.status_code == 200
    assert RecordingChatService.last_call["user_input"] == "正常聊天"


def test_chat_api_passes_trusted_audio_observation_to_chat_service(
    monkeypatch, tmp_path: Path
) -> None:
    RecordingChatService.last_call = {}
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "audio-contract-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())

    async def fake_v2_handler(**_kwargs):
        return None

    monkeypatch.setattr("app.main.try_handle_database_v2_platform_message", fake_v2_handler)
    monkeypatch.setattr(
        "app.main.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            json={
                "user_input": "[语音转写：我今天有点难受]",
                "session_id": "qq-audio",
                "user_id": "qq-fake",
                "platform": "qq",
                "platform_user_id": "fake-qq",
                "input_source": "audio",
                "input_quality_passed": True,
                "input_emotion": "sad",
                "input_emotion_source": "emotion2vec",
                "input_emotion_confidence": 0.92,
            },
        )
    )

    assert response.status_code == 200
    assert RecordingChatService.last_call["input_source"] == "audio"
    assert RecordingChatService.last_call["input_emotion"] == "sad"
    assert RecordingChatService.last_call["input_emotion_source"] == "emotion2vec"
    assert RecordingChatService.last_call["input_emotion_confidence"] == 0.92


def test_chat_api_uses_database_v2_repository_for_enabled_platform_chat(monkeypatch) -> None:
    class CapturingChatService:
        last_repository = None
        last_call: dict[str, object] = {}

        def __init__(self, settings, repository=None, **kwargs) -> None:
            type(self).last_repository = repository

        async def reply(self, user_input: str, **kwargs):
            type(self).last_call = {"user_input": user_input, **kwargs}
            return ChatResponse(
                text="ok",
                provider="local",
                model="fake",
                used_live_api=False,
                fallback_used=True,
            )

    fake_repository = object()

    async def fake_v2_handler(**kwargs):
        return None

    monkeypatch.setenv("DATABASE_V2_ENABLED", "true")
    monkeypatch.setattr("app.main.settings", load_settings())
    monkeypatch.setattr("app.main.try_handle_database_v2_platform_message", fake_v2_handler)
    monkeypatch.setattr("app.main.build_database_v2_chat_repository", lambda settings: fake_repository)
    monkeypatch.setattr("app.main.ChatService", CapturingChatService)

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat",
            json={
                "user_input": "正常微信聊天",
                "session_id": "wechat-session",
                "user_id": "hermes-user",
                "platform": "wechat",
                "platform_user_id": "wx-open-id-1",
            },
        )
    )

    assert response.status_code == 200
    assert CapturingChatService.last_repository is fake_repository
    assert CapturingChatService.last_call["user_id"] == "wechat-wx-open-id-1"


def test_audio_transcribe_file_api_returns_transcript(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.transcribe_audio_file",
        lambda audio_path: FakeFileAsrEngine().transcribe_file(audio_path) and {
            "text": "欢迎大家来体验语音识别模型。",
            "provider": "fake-asr",
            "model": "fake-file-model",
            "audio_path": str(audio_path),
            "latency_ms": 1.0,
            "error": None,
        },
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/transcribe/file",
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["text"] == "欢迎大家来体验语音识别模型。"
    assert body["provider"] == "fake-asr"
    assert body["model"] == "fake-file-model"
    assert body["selected_candidate_id"] == "primary"


def test_audio_upload_enforces_size_limit_before_transcription(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, audio_upload_max_bytes=4),
    )
    called = False

    def should_not_transcribe(_audio_path: Path):
        nonlocal called
        called = True
        raise AssertionError("oversized upload reached ASR")

    monkeypatch.setattr(main, "transcribe_audio_file", should_not_transcribe)

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/transcribe/file",
            files={"file": ("sample.wav", b"12345", "audio/wav")},
        )
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "audio upload exceeds 4 bytes"
    assert called is False


def test_audio_upload_rejects_unsupported_extension() -> None:
    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/transcribe/file",
            files={"file": ("sample.exe", b"MZ", "application/octet-stream")},
        )
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "unsupported audio file extension"


def test_audio_transcribe_file_api_removes_temp_upload_after_processing(monkeypatch) -> None:
    captured: dict[str, Path] = {}

    def fake_transcribe(audio_path: Path) -> dict[str, object]:
        captured["path"] = audio_path
        assert audio_path.exists()
        return {
            "text": "voice transcript",
            "provider": "fake-asr",
            "model": "fake-file-model",
            "audio_path": str(audio_path),
            "latency_ms": 1.0,
        }

    monkeypatch.setattr(main, "transcribe_audio_file", fake_transcribe)

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/transcribe/file",
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    assert response.status_code == 200
    assert not captured["path"].exists()


def test_audio_chat_prepare_file_api_skips_optional_emotion_analysis(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fast_transcribe(audio_path: Path, *, include_emotion: bool = True) -> AsrFileResponse:
        received["include_emotion"] = include_emotion
        return AsrFileResponse(
            text="voice sample transcript",
            provider="fake-asr",
            model="fake-file-model",
            audio_path=str(audio_path),
            latency_ms=1.0,
        )

    monkeypatch.setattr("app.main.transcribe_audio_file", fast_transcribe)

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/chat/prepare/file",
            data={"session_id": "audio-prepare-s1", "user_id": "audio-prepare-u1"},
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert received == {"include_emotion": False}
    assert body["transcript_text"] == "voice sample transcript"
    assert body["chat_input_text"] == "voicesampletranscript"
    assert body["chat_bypassed_due_to_asr_quality"] is False
    assert body["clarification_reply"] is None


def test_audio_stream_timeout_returns_a_retryable_reply() -> None:
    async def slow_reply():
        await asyncio.sleep(0.02)
        yield "late reply"

    async def collect() -> list[str]:
        return [
            chunk
            async for chunk in main.limit_audio_stream_to_realtime_budget(
                slow_reply(),
                timeout_seconds=0.001,
            )
        ]

    assert asyncio.run(collect()) == ["\u8fd9\u6b21\u56de\u590d\u8017\u65f6\u8fc7\u957f\uff0c\u8bf7\u70b9\u51fb\u91cd\u8bd5\u3002"]


def test_audio_chat_stream_applies_the_realtime_reply_budget(monkeypatch) -> None:
    class SlowRuntime:
        async def stream(self, *_args: object, **_kwargs: object):
            await asyncio.sleep(0.02)
            yield "late reply"

    async def allow_local_web_request(request: ChatRequest, *_args: object) -> ChatRequest:
        return request

    monkeypatch.setattr(main, "_authenticated_web_request", allow_local_web_request)
    monkeypatch.setattr(main, "build_head_runtime", lambda: SlowRuntime())
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, voice_chat_reply_timeout_seconds=0.001),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/chat/stream",
            json={
                "user_input": "voice request",
                "session_id": "audio-timeout-s1",
                "user_id": "audio-timeout-u1",
                "input_source": "audio",
            },
        )
    )

    assert response.status_code == 200
    assert response.text == "\u8fd9\u6b21\u56de\u590d\u8017\u65f6\u8fc7\u957f\uff0c\u8bf7\u70b9\u51fb\u91cd\u8bd5\u3002"


def test_audio_chat_file_api_uses_transcript_for_chat(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.transcribe_audio_file",
        lambda audio_path: AsrFileResponse(
            text="欢迎大家来体验语音识别模型。",
            provider="fake-asr",
            model="fake-file-model",
            audio_path=str(audio_path),
            latency_ms=1.0,
        ),
    )
    monkeypatch.setattr("app.main.ChatService", lambda settings, **kwargs: ChatService(
        settings,
        client=FakeSuccessClient(),
        repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
    ))

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/chat/file",
            data={"session_id": "audio-s1", "user_id": "audio-u1"},
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["transcript_text"] == "欢迎大家来体验语音识别模型。"
    assert body["chat_input_text"] == "欢迎大家来体验语音识别模型。"
    assert body["chat_bypassed_due_to_asr_quality"] is False
    assert body["chat_bypass_reasons"] == []
    assert body["reply_text"]
    assert body["asr"]["text"] == "欢迎大家来体验语音识别模型。"
    assert body["chat"]["used_live_api"] is True


def test_audio_chat_file_api_clarifies_blocking_low_quality_asr(monkeypatch, tmp_path: Path) -> None:
    RecordingChatService.last_call = {}
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "audio-quality-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())
    monkeypatch.setattr(
        "app.main.transcribe_audio_file",
        lambda audio_path: AsrFileResponse(
            text="������",
            provider="fake-asr",
            model="fake-file-model",
            audio_path=str(audio_path),
            latency_ms=1.0,
            quality_passed=False,
            quality_score=0.0,
            quality_reasons=["mojibake_or_replacement_char", "low_chinese_ratio"],
        ),
    )
    monkeypatch.setattr(
        "app.main.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/chat/file",
            data={"session_id": "audio-quality-s1", "user_id": "audio-quality-u1"},
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["asr"]["quality_passed"] is False
    assert body["asr"]["quality_reasons"] == [
        "mojibake_or_replacement_char",
        "low_chinese_ratio",
    ]
    assert body["chat_input_text"] == "������"
    assert body["chat_bypassed_due_to_asr_quality"] is True
    assert body["chat_bypass_reasons"] == [
        "mojibake_or_replacement_char",
        "low_chinese_ratio",
    ]
    assert body["reply_text"] == "我刚才没听清，你短一点再说一遍。"
    assert body["chat"]["provider"] == "local"
    assert RecordingChatService.last_call == {}


def test_audio_chat_file_api_cleans_punctuation_collision_before_chat(monkeypatch, tmp_path: Path) -> None:
    RecordingChatService.last_call = {}
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "audio-punctuation-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())
    monkeypatch.setattr(
        "app.main.transcribe_audio_file",
        lambda audio_path: AsrFileResponse(
            text="成，那就唠唠，。你最近有没有碰上什么怪事？，",
            provider="fake-asr",
            model="fake-file-model",
            audio_path=str(audio_path),
            latency_ms=1.0,
            quality_passed=False,
            quality_score=0.65,
            quality_reasons=["punctuation_collision"],
        ),
    )
    monkeypatch.setattr(
        "app.main.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/chat/file",
            data={"session_id": "audio-punctuation-s1", "user_id": "audio-punctuation-u1"},
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["chat_input_text"] == "成，那就唠唠。你最近有没有碰上什么怪事？"
    assert body["chat_bypassed_due_to_asr_quality"] is False
    assert RecordingChatService.last_call["user_input"] == "成，那就唠唠。你最近有没有碰上什么怪事？"
    assert RecordingChatService.last_call["input_quality_passed"] is False
    assert RecordingChatService.last_call["input_quality_reasons"] == ["punctuation_collision"]


def test_audio_chat_file_api_passes_asr_emotion_to_chat(monkeypatch, tmp_path: Path) -> None:
    RecordingChatService.last_call = {}
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "audio-emotion-storage"))
    monkeypatch.setattr("app.main.settings", load_settings())
    monkeypatch.setattr(
        "app.main.transcribe_audio_file",
        lambda audio_path: AsrFileResponse(
            text="欢迎大家来体验语音识别模型。",
            provider="fake-asr",
            model="fake-file-model",
            audio_path=str(audio_path),
            latency_ms=1.0,
            emotion="happy",
            emotion_source="sensevoice_tag",
            emotion_confidence=0.82,
        ),
    )
    monkeypatch.setattr(
        "app.main.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/api/v1/audio/chat/file",
            data={"session_id": "audio-emotion-s1", "user_id": "audio-emotion-u1"},
            files={"file": ("sample.wav", b"RIFF", "audio/wav")},
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["asr"]["emotion"] == "happy"
    assert RecordingChatService.last_call["input_emotion"] == "happy"
    assert RecordingChatService.last_call["input_emotion_source"] == "sensevoice_tag"
    assert RecordingChatService.last_call["input_emotion_confidence"] == 0.82


def test_openai_compat_models_endpoint_returns_hutao_model() -> None:
    response = asyncio.run(request_app("GET", "/v1/models"))

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    model_ids = {item["id"] for item in body["data"]}
    assert "hutao-chatcore" in model_ids
    assert "xiaohe-chatcore" not in model_ids


def test_openai_compat_chat_completion_uses_latest_user_message(monkeypatch, tmp_path: Path) -> None:
    RecordingChatService.last_call = {}
    monkeypatch.setenv("DATABASE_V2_ENABLED", "false")
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "openai-compat-storage"))
    monkeypatch.setattr("app.openai_compat.settings", load_settings())
    monkeypatch.setattr(
        "app.openai_compat.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
            audit_logger=ModelInvocationAuditLogger(tmp_path / "openai-compat-audit.jsonl"),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "hutao-chatcore",
                "user": "wechat-user-1",
                "messages": [
                    {"role": "system", "content": "ignore"},
                    {"role": "user", "content": "上一轮。"},
                    {"role": "assistant", "content": "上一轮回复。"},
                    {"role": "user", "content": "微信里接一句。"},
                ],
            },
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["object"] == "chat.completion"
    assert body["model"] == "hutao-chatcore"
    assert str(body["id"]).startswith("chatcmpl-hutao-")
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"]
    assert RecordingChatService.last_call["user_input"] == "微信里接一句。"
    assert RecordingChatService.last_call["session_id"] == "openai-compat-wechat-user-1"
    assert RecordingChatService.last_call["user_id"] == "wechat-user-1"


def test_openai_compat_authenticated_mode_uses_server_identity(monkeypatch, tmp_path: Path) -> None:
    from app.auth.service import StoredSession

    class FakePublicAuthService:
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            assert session_token == "valid-session"
            assert kwargs == {"csrf_token": "csrf-value", "require_csrf": True}
            return StoredSession(
                id="server-session",
                user_id="web-user",
                profile_id="profile-from-session",
                token_hash="x" * 64,
                csrf_secret_hash="y" * 64,
                expires_at="2026-07-26T12:00:00+00:00",  # type: ignore[arg-type]
                revoked_at=None,
            )

    RecordingChatService.last_call = {}
    monkeypatch.setattr(main, "public_web_auth_configured", True)
    monkeypatch.setattr(main, "public_web_auth_service", FakePublicAuthService())
    monkeypatch.setenv("DATABASE_V2_ENABLED", "false")
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "openai-auth-storage"))
    monkeypatch.setattr("app.openai_compat.settings", load_settings())
    monkeypatch.setattr(
        "app.openai_compat.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
            audit_logger=ModelInvocationAuditLogger(tmp_path / "openai-auth-audit.jsonl"),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/v1/chat/completions",
            headers={"Cookie": "hutao_session=valid-session", "X-CSRF-Token": "csrf-value"},
            json={
                "model": "hutao-chatcore",
                "user": "attacker-user",
                "user_id": "attacker-profile",
                "session_id": "attacker-session",
                "messages": [{"role": "user", "content": "authenticated request"}],
            },
        )
    )

    assert response.status_code == 200
    assert RecordingChatService.last_call["user_id"] == "profile-from-session"
    assert RecordingChatService.last_call["session_id"] == "server-session"


def test_openai_compat_chat_completion_accepts_text_content_parts(monkeypatch, tmp_path: Path) -> None:
    RecordingChatService.last_call = {}
    monkeypatch.setenv("DATABASE_V2_ENABLED", "false")
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    monkeypatch.setenv("JSONL_STORAGE_DIR", str(tmp_path / "openai-compat-parts-storage"))
    monkeypatch.setattr("app.openai_compat.settings", load_settings())
    monkeypatch.setattr(
        "app.openai_compat.ChatService",
        lambda settings, **kwargs: RecordingChatService(
            settings,
            client=FakeSuccessClient(),
            repository=JsonlChatRepository(Path(settings.jsonl_storage_dir)),
            audit_logger=ModelInvocationAuditLogger(tmp_path / "openai-compat-parts-audit.jsonl"),
        ),
    )

    response = asyncio.run(
        request_app(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "hutao-chatcore",
                "session_id": "hermes-weixin-chat-1",
                "user_id": "hermes-user-1",
                "platform": "wechat",
                "platform_user_id": "wx-open-id-1",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "第一句。"},
                            {"type": "text", "text": "第二句。"},
                        ],
                    }
                ],
            },
        )
    )

    assert response.status_code == 200
    assert RecordingChatService.last_call["user_input"] == "第一句。\n第二句。"
    assert RecordingChatService.last_call["session_id"] == "hermes-weixin-chat-1"
    assert RecordingChatService.last_call["user_id"] == "hermes-user-1"
    assert RecordingChatService.last_call["platform"] == "wechat"
    assert RecordingChatService.last_call["platform_user_id"] == "wx-open-id-1"


def test_openai_compat_rejects_unsupported_image_content_instead_of_dropping_it() -> None:
    response = asyncio.run(
        request_app(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "hutao-chatcore",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请看这张图"},
                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
                        ],
                    }
                ],
            },
        )
    )

    assert response.status_code == 400
    assert "image_url content is not supported" in response.json()["detail"]


def test_openai_compat_chat_completion_uses_database_v2_for_wechat_command(monkeypatch) -> None:
    RecordingChatService.last_call = {}

    async def fake_v2_handler(**kwargs):
        assert kwargs["platform"] == "wechat"
        assert kwargs["platform_user_id"] == "wx-open-id-1"
        assert kwargs["message_text"] == "胡桃 最近聊天"
        return ChatResponse(
            text="recent chats handled",
            provider="local",
            model="database-v2-platform-command",
            used_live_api=False,
            fallback_used=True,
            error="recent_chats_loaded",
        )

    monkeypatch.setattr("app.openai_compat.try_handle_database_v2_platform_message", fake_v2_handler)
    monkeypatch.setattr("app.openai_compat.ChatService", lambda settings, **kwargs: RecordingChatService(settings))

    response = asyncio.run(
        request_app(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "hutao-chatcore",
                "session_id": "hermes-weixin-chat-1",
                "user_id": "hermes-user-1",
                "platform": "wechat",
                "platform_user_id": "wx-open-id-1",
                "messages": [{"role": "user", "content": "胡桃 最近聊天"}],
            },
        )
    )

    body = response.json()
    assert response.status_code == 200
    assert body["choices"][0]["message"]["content"] == "recent chats handled"
    assert RecordingChatService.last_call == {}


def test_openai_compat_database_v2_stream_uses_content_then_terminal_chunk(monkeypatch) -> None:
    async def fake_v2_handler(**kwargs):
        return ChatResponse(
            text="recent chats handled",
            provider="local",
            model="database-v2-platform-command",
            used_live_api=False,
            fallback_used=True,
        )

    monkeypatch.setattr("app.openai_compat.try_handle_database_v2_platform_message", fake_v2_handler)

    response = asyncio.run(
        request_app(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "hutao-chatcore",
                "stream": True,
                "platform": "wechat",
                "platform_user_id": "wx-open-id-1",
                "messages": [{"role": "user", "content": "胡桃 最近聊天"}],
            },
        )
    )

    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert events[0]["choices"][0] == {
        "index": 0,
        "delta": {"content": "recent chats handled"},
        "finish_reason": None,
    }
    assert events[1]["choices"][0] == {
        "index": 0,
        "delta": {},
        "finish_reason": "stop",
    }
    assert response.text.endswith("data: [DONE]\n\n")


def test_openai_compat_uses_database_v2_repository_for_enabled_wechat_chat(monkeypatch) -> None:
    class CapturingChatService:
        last_repository = None
        last_call: dict[str, object] = {}

        def __init__(self, settings, repository=None, **kwargs) -> None:
            type(self).last_repository = repository

        async def reply(self, user_input: str, **kwargs):
            type(self).last_call = {"user_input": user_input, **kwargs}
            return ChatResponse(
                text="ok",
                provider="local",
                model="fake",
                used_live_api=False,
                fallback_used=True,
            )

    fake_repository = object()

    async def fake_v2_handler(**kwargs):
        return None

    monkeypatch.setenv("DATABASE_V2_ENABLED", "true")
    monkeypatch.setattr("app.openai_compat.settings", load_settings())
    monkeypatch.setattr("app.openai_compat.try_handle_database_v2_platform_message", fake_v2_handler)
    monkeypatch.setattr("app.openai_compat.build_database_v2_chat_repository", lambda settings: fake_repository)
    monkeypatch.setattr("app.openai_compat.ChatService", CapturingChatService)

    response = asyncio.run(
        request_app(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "xiaohe-chatcore",
                "session_id": "hermes-weixin-chat-1",
                "user_id": "hermes-user-1",
                "platform": "wechat",
                "platform_user_id": "wx-open-id-1",
                "messages": [{"role": "user", "content": "普通微信聊天"}],
            },
        )
    )

    assert response.status_code == 200
    assert CapturingChatService.last_repository is fake_repository
    assert CapturingChatService.last_call["user_id"] == "wechat-wx-open-id-1"
