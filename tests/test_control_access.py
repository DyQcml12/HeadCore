from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

from app.auth.service import AccountProfile, AuthenticatedAccount, AuthenticationError
from app.control.access import configure_control_web_runtime
from app.control.routes import router as control_router


class FakeWebAuthService:
    def __init__(self, account: AuthenticatedAccount | None) -> None:
        self.account = account

    async def require_session(self, *, session_token, csrf_token=None, require_csrf=False):
        if session_token != "session-owner":
            raise AuthenticationError("authentication required")
        if require_csrf and csrf_token != "csrf-owner":
            raise AuthenticationError("csrf validation failed")
        return object()

    async def current_account(self, *, session_token):
        if session_token != "session-owner" or self.account is None:
            raise AuthenticationError("authentication required")
        return self.account


def account(email: str) -> AuthenticatedAccount:
    now = datetime.now(timezone.utc)
    return AuthenticatedAccount(
        profile=AccountProfile(
            user_id="user-1",
            profile_id="profile-1",
            display_name="Owner",
            email_normalized=email,
            email_verified=True,
            created_at=now - timedelta(days=1),
        ),
        session_expires_at=now + timedelta(hours=1),
    )


async def request(app: FastAPI, method: str, path: str, **kwargs: object) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


async def remote_request(app: FastAPI, method: str, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("10.0.0.7", 4321)),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path)


@pytest.fixture(autouse=True)
def reset_control_runtime():
    configure_control_web_runtime(enabled=False, auth_service=None, admin_emails="")
    yield
    configure_control_web_runtime(enabled=False, auth_service=None, admin_emails="")


def test_control_page_redirects_anonymous_web_request_to_login() -> None:
    app = FastAPI()
    app.include_router(control_router)
    configure_control_web_runtime(
        enabled=True,
        auth_service=FakeWebAuthService(None),  # type: ignore[arg-type]
        admin_emails="owner@example.com",
    )

    response = asyncio.run(request(app, "GET", "/control", follow_redirects=False))

    assert response.status_code == 307
    assert response.headers["location"] == "/auth?return_to=%2Fcontrol"


def test_control_page_is_loopback_only_by_default() -> None:
    app = FastAPI()
    app.include_router(control_router)

    response = asyncio.run(remote_request(app, "GET", "/control"))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "control_loopback_only"


def test_control_api_rejects_a_logged_in_non_owner() -> None:
    app = FastAPI()
    app.include_router(control_router)
    configure_control_web_runtime(
        enabled=True,
        auth_service=FakeWebAuthService(account("member@example.com")),  # type: ignore[arg-type]
        admin_emails="owner@example.com",
    )

    response = asyncio.run(
        request(app, "GET", "/api/control/status", cookies={"hutao_session": "session-owner"})
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "control_admin_required"


def test_control_api_allows_owner_and_requires_csrf_for_writes() -> None:
    app = FastAPI()
    app.include_router(control_router)
    configure_control_web_runtime(
        enabled=True,
        auth_service=FakeWebAuthService(account("owner@example.com")),  # type: ignore[arg-type]
        admin_emails="owner@example.com",
    )

    read_response = asyncio.run(
        request(app, "GET", "/api/control/status", cookies={"hutao_session": "session-owner"})
    )
    write_response = asyncio.run(
        request(
            app,
            "POST",
            "/api/control/config",
            cookies={"hutao_session": "session-owner"},
            json={"values": {}},
        )
    )

    assert read_response.status_code == 200
    assert write_response.status_code == 403
    assert write_response.json()["detail"]["code"] == "csrf_validation_failed"
