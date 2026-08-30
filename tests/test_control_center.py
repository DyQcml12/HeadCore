from __future__ import annotations

import asyncio

import httpx
import pytest

from app.control.health_checks import build_control_status
from app.control.service_manager import list_services
from app.main import app


async def request_app(method: str, url: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, url, **kwargs)


def test_control_page_is_headcore_operations_console_without_bot_routes() -> None:
    response = asyncio.run(request_app("GET", "/control"))

    assert response.status_code == 200
    assert "HeadCore 控制台" in response.text
    assert "核心运行时" in response.text
    assert "客户端与发布" in response.text
    assert "能力服务" in response.text
    assert "运行诊断" in response.text
    assert "/control/qq" not in response.text
    assert "/control/weixin" not in response.text
    assert "/weixin" not in response.text
    assert "NapCat" not in response.text
    assert "Hermes" not in response.text


@pytest.mark.parametrize("path", ("/control/qq", "/control/weixin", "/weixin"))
def test_retired_bot_pages_are_not_published(path: str) -> None:
    response = asyncio.run(request_app("GET", path))

    assert response.status_code == 404


def test_control_static_assets_are_published() -> None:
    js_response = asyncio.run(request_app("GET", "/control/app.js"))
    css_response = asyncio.run(request_app("GET", "/control/style.css"))

    assert js_response.status_code == 200
    assert "renderOperations" in js_response.text
    assert "QQ" not in js_response.text
    assert css_response.status_code == 200
    assert "minmax" in css_response.text
    assert "html,body{width:100%;min-width:0}" in css_response.text
    assert "main{min-width:0;" in css_response.text
    assert "main{width:100%" not in css_response.text


def test_control_status_reports_core_and_capabilities_without_bot_guides() -> None:
    body = build_control_status()
    ids = {item["id"] for item in body["items"]}

    assert {"hutao_core", "gpt_sovits", "world_awareness"} <= ids
    assert "ollama" not in ids
    assert set(body["guides"]) == {"clients"}
    assert "qq_bridge" not in ids
    assert "hermes_runtime" not in ids


def test_service_registry_excludes_bot_runtimes() -> None:
    ids = {service["id"] for service in list_services()}

    assert ids == {"hutao_core", "gpt_sovits"}


def test_operations_status_has_no_platform_bot_components() -> None:
    response = asyncio.run(request_app("GET", "/api/control/operations/status"))
    components = response.json()["components"]

    assert response.status_code == 200
    assert "core_api" in components
    assert "qq_bridge" not in components
    assert "weixin" not in components


def test_bot_specific_control_apis_are_not_published() -> None:
    for path in ("/api/control/weixin/status", "/api/control/bot-logs/qq"):
        response = asyncio.run(request_app("GET", path))
        assert response.status_code == 404


def test_control_world_model_document_is_not_published() -> None:
    response = asyncio.run(request_app("GET", "/control/docs/world-model"))

    assert response.status_code == 404
