from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.core.config import load_settings
from app.desktop import config_store
from app.desktop.router import create_desktop_router
from scripts.windows.launcher import resolve_install_root


def test_windows_launcher_uses_executable_directory_when_frozen(tmp_path: Path) -> None:
    executable = tmp_path / "HuTaoAssistant.exe"
    assert resolve_install_root(frozen=True, executable=str(executable)) == tmp_path.resolve()


def test_local_config_masks_and_preserves_api_keys(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    runtime_path = tmp_path / "runtime.env"
    monkeypatch.setattr(config_store, "LOCAL_APP_ROOT", tmp_path)
    monkeypatch.setattr(config_store, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_store, "RUNTIME_ENV_PATH", runtime_path)
    monkeypatch.setattr(config_store, "SECRETS_PATH", tmp_path / "secrets.dpapi")

    config_store.save_config({"text": {"api_key": "secret-value", "model": "demo-model"}})
    public = config_store.public_config()
    assert "api_key" not in public["text"]
    assert public["text"]["api_key_configured"] is True

    config_store.save_config({"text": {"model": "next-model", "api_key": ""}})
    assert "api_key" not in config_store.load_config()["text"]
    assert config_store.secret_for(config_store.load_config(), "text") == "secret-value"
    assert "secret-value" not in runtime_path.read_text(encoding="utf-8")


def test_vision_route_does_not_call_vision_for_text_only_requests() -> None:
    application = FastAPI()
    application.include_router(create_desktop_router(load_settings()))

    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/v1/desktop/vision/route", json={"has_image": False})

    response = asyncio.run(run())
    assert response.status_code == 200
    assert response.json()["route"] == "text-only"


def test_vision_route_selects_multimodal_text_model(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(config_store, "LOCAL_APP_ROOT", tmp_path)
    monkeypatch.setattr(config_store, "RUNTIME_ENV_PATH", tmp_path / "runtime.env")
    monkeypatch.setattr(config_store, "SECRETS_PATH", tmp_path / "secrets.dpapi")
    config_store.save_config({"text": {"capability": "multimodal"}})

    application = FastAPI()
    application.include_router(create_desktop_router(load_settings()))

    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/api/v1/desktop/vision/route", json={"has_image": True})

    response = asyncio.run(run())
    assert response.status_code == 200
    assert response.json()["route"] == "text-model-multimodal"
