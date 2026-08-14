from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

import app.main as main
from app.core.config import load_settings
from app.main import app
from app.persona_management.sandbox import (
    LocalSandboxPersonaService,
    SandboxPersonaNotFoundError,
)
from app.services.chat_service import ChatService
from app.storage.chat_repository import JsonlChatRepository


class RecordingClient:
    def __init__(self) -> None:
        self.system_prompt = ""

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        return "我们先把这件事拆成一个清楚的小步骤。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):
        self.system_prompt = system_prompt
        yield "我们先把这件事拆成一个清楚的小步骤。"


async def request_app(method: str, url: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, url, **kwargs)


def test_local_sandbox_persona_is_durable_and_owner_scoped(tmp_path: Path) -> None:
    service = LocalSandboxPersonaService(tmp_path)
    persona = asyncio.run(
        service.create(
            owner_id="local-user-a",
            name="Calm guide",
            traits=("clear", "warm", "direct"),
            detail="Use short sentences and distinguish facts from assumptions.",
        )
    )

    reloaded_service = LocalSandboxPersonaService(tmp_path)
    listed = asyncio.run(reloaded_service.list_for_owner("local-user-a"))

    assert [item.persona_id for item in listed] == [persona.persona_id]
    assert listed[0].name == "Calm guide"
    with pytest.raises(SandboxPersonaNotFoundError):
        asyncio.run(reloaded_service.get_for_owner(persona.persona_id, owner_id="local-user-b"))


def test_selected_sandbox_persona_is_injected_into_chat_prompt(tmp_path: Path) -> None:
    persona_store = LocalSandboxPersonaService(tmp_path / "personas")
    persona = asyncio.run(
        persona_store.create(
            owner_id="user-a",
            name="Research companion",
            traits=("precise", "calm"),
            detail="Use short evidence-based answers and say when something is uncertain.",
        )
    )
    client = RecordingClient()
    storage_dir = tmp_path / "chat-storage"
    service = ChatService(
        load_settings(),
        client=client,
        repository=JsonlChatRepository(storage_dir),
        sandbox_persona_projection_provider=persona_store,
    )

    asyncio.run(
        service.reply(
            "Help me decide what to test first.",
            session_id="sandbox-session",
            user_id="user-a",
            sandbox_persona_id=persona.persona_id,
        )
    )

    assert "Research companion" in client.system_prompt
    assert "Use short evidence-based answers" in client.system_prompt
    assert "HeadCore" in client.system_prompt
    invocation = json.loads((storage_dir / "model_invocations.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    metadata = invocation["request_metadata_json"]
    assert metadata["sandbox_persona_id"] == persona.persona_id
    assert metadata["sandbox_persona_status"] == "ready"


def test_sandbox_persona_api_hides_other_local_owner_records(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(main.sandbox_persona_service, "_path", tmp_path / "sandbox-personas.json")

    created = asyncio.run(
        request_app(
            "POST",
            "/api/v1/sandbox/personas",
            json={
                "user_id": "local-user-a",
                "name": "API persona",
                "traits": ["warm"],
                "detail": "Keep responses compact.",
            },
        )
    )

    assert created.status_code == 201
    persona_id = created.json()["persona_id"]
    own_list = asyncio.run(
        request_app("GET", "/api/v1/sandbox/personas?user_id=local-user-a")
    )
    other_read = asyncio.run(
        request_app(
            "GET",
            f"/api/v1/sandbox/personas/{persona_id}?user_id=local-user-b",
        )
    )

    assert [item["persona_id"] for item in own_list.json()] == [persona_id]
    assert other_read.status_code == 404
