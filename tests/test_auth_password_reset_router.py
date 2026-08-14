from __future__ import annotations

import asyncio
import importlib
import importlib.util

import httpx
from fastapi import FastAPI


class RecordingResetService:
    def __init__(self) -> None:
        self.requested: list[str] = []
        self.confirmed: list[tuple[str, str]] = []

    async def request(self, *, email: str) -> None:
        self.requested.append(email)

    async def confirm(self, *, token: str, password: str) -> None:
        self.confirmed.append((token, password))


async def request(app: FastAPI, method: str, path: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def password_reset_router_module():
    spec = importlib.util.find_spec("app.auth.password_reset_router")
    assert spec is not None, "password reset router must be provided"
    return importlib.import_module("app.auth.password_reset_router")


def test_password_reset_request_uses_a_generic_accepted_response() -> None:
    module = password_reset_router_module()
    service = RecordingResetService()
    app = FastAPI()
    app.include_router(module.create_password_reset_router(service))

    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/password-reset/request",
            json={"email": "reader@example.com"},
        )
    )

    assert response.status_code == 202
    assert response.json() == {"status": "request_accepted"}
    assert service.requested == ["reader@example.com"]
    assert "token" not in response.text


def test_password_reset_confirmation_accepts_token_only_in_post_body() -> None:
    module = password_reset_router_module()
    service = RecordingResetService()
    app = FastAPI()
    app.include_router(module.create_password_reset_router(service))

    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/password-reset/confirm",
            json={"token": "opaque-reset-token", "password": "ChangedPassword!2026"},
        )
    )

    assert response.status_code == 200
    assert response.json() == {"status": "password_updated"}
    assert service.confirmed == [("opaque-reset-token", "ChangedPassword!2026")]
