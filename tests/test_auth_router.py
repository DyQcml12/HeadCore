import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI

from app.auth.passwords import hash_password
from app.auth.router import create_auth_router
from app.auth.rate_limit import AuthRateLimitService, RateLimitState
from app.auth.service import AuthService, StoredSession, WebUser


@dataclass(frozen=True)
class FakeAccountProfile:
    user_id: str
    profile_id: str
    display_name: str
    email_normalized: str
    email_verified: bool
    created_at: datetime


class RouterAuthRepository:
    def __init__(self) -> None:
        self.user = WebUser(
            id="user-1",
            profile_id="profile-1",
            email_normalized="reader@example.com",
            password_hash=hash_password("SafePassword!2026"),
            status="active",
        )
        self.session: StoredSession | None = None

    async def find_user_by_email(self, *, email_normalized: str) -> WebUser | None:
        return self.user if email_normalized == self.user.email_normalized else None

    async def find_account_by_user_id(self, *, user_id: str) -> FakeAccountProfile | None:
        if user_id != self.user.id:
            return None
        return FakeAccountProfile(
            user_id=self.user.id,
            profile_id=self.user.profile_id,
            display_name="往生堂访客",
            email_normalized=self.user.email_normalized,
            email_verified=True,
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

    async def create_session(self, **values: object) -> StoredSession:
        self.session = StoredSession(
            id="session-1",
            user_id="user-1",
            profile_id="profile-1",
            token_hash=str(values["token_hash"]),
            csrf_secret_hash=str(values["csrf_secret_hash"]),
            expires_at=values["expires_at"],  # type: ignore[arg-type]
            revoked_at=None,
        )
        return self.session

    async def find_session_by_token_hash(self, *, token_hash: str) -> StoredSession | None:
        return self.session if self.session and self.session.token_hash == token_hash else None

    async def revoke_session(self, *, session_id: str, revoked_at: datetime) -> None:
        assert self.session is not None
        self.session = StoredSession(**{**self.session.__dict__, "revoked_at": revoked_at})


async def request(app: FastAPI, method: str, path: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def test_login_sets_http_only_session_cookie_and_returns_csrf_value() -> None:
    app = FastAPI()
    app.include_router(create_auth_router(AuthService(RouterAuthRepository(), session_lifetime=timedelta(hours=1))))

    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": "reader@example.com", "password": "SafePassword!2026"},
        )
    )

    assert response.status_code == 200
    assert response.json()["profile_id"] == "profile-1"
    assert response.json()["csrf_token"]
    cookie = response.headers["set-cookie"]
    assert "hutao_session=" in cookie
    assert "hutao_csrf=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_mini_program_login_returns_a_bearer_session_without_setting_browser_cookies() -> None:
    app = FastAPI()
    app.include_router(create_auth_router(AuthService(RouterAuthRepository(), session_lifetime=timedelta(hours=1))))

    login = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/mobile/login",
            json={"email": "reader@example.com", "password": "SafePassword!2026"},
        )
    )

    assert login.status_code == 200
    body = login.json()
    assert body["profile_id"] == "profile-1"
    assert body["access_token"]
    assert body["csrf_token"]
    assert "set-cookie" not in login.headers

    account = asyncio.run(
        request(
            app,
            "GET",
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
    )

    assert account.status_code == 200
    assert account.json()["profile_id"] == "profile-1"


def test_current_account_returns_only_the_authenticated_profile() -> None:
    repository = RouterAuthRepository()
    app = FastAPI()
    app.include_router(create_auth_router(AuthService(repository)))
    login = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": "reader@example.com", "password": "SafePassword!2026"},
        )
    )

    response = asyncio.run(
        request(
            app,
            "GET",
            "/api/v1/auth/me",
            headers={"Cookie": f"hutao_session={login.cookies.get('hutao_session')}"},
        )
    )

    assert response.status_code == 200
    body = response.json()
    assert {key: value for key, value in body.items() if key != "session_expires_at"} == {
        "profile_id": "profile-1",
        "display_name": "往生堂访客",
        "email": "reader@example.com",
        "email_verified": True,
        "created_at": "2026-07-26T00:00:00+00:00",
    }
    assert datetime.fromisoformat(body["session_expires_at"]) > datetime.now(timezone.utc)


def test_current_account_rejects_a_request_without_a_session_cookie() -> None:
    app = FastAPI()
    app.include_router(create_auth_router(AuthService(RouterAuthRepository())))

    response = asyncio.run(request(app, "GET", "/api/v1/auth/me"))

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"


def test_logout_requires_csrf_header_and_revokes_current_session() -> None:
    repository = RouterAuthRepository()
    app = FastAPI()
    app.include_router(create_auth_router(AuthService(repository)))
    login = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": "reader@example.com", "password": "SafePassword!2026"},
        )
    )
    session_cookie = login.cookies.get("hutao_session")
    csrf_token = login.json()["csrf_token"]

    rejected = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/logout",
            headers={"Cookie": f"hutao_session={session_cookie}"},
        )
    )
    accepted = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/logout",
            headers={
                "Cookie": f"hutao_session={session_cookie}",
                "X-CSRF-Token": csrf_token,
            },
        )
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 204
    assert repository.session is not None
    assert repository.session.revoked_at is not None


def test_login_returns_429_when_rate_limited() -> None:
    class BlockingRateRepository:
        async def record_attempt(self, **values: object) -> RateLimitState:
            return RateLimitState(attempt_count=6, blocked_until=values["blocked_until"])  # type: ignore[arg-type]

    app = FastAPI()
    app.include_router(
        create_auth_router(
            AuthService(RouterAuthRepository()),
            login_rate_limiter=AuthRateLimitService(BlockingRateRepository()),  # type: ignore[arg-type]
        )
    )

    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/login",
            json={"email": "reader@example.com", "password": "SafePassword!2026"},
        )
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "try again later"
