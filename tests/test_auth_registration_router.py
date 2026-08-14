import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI

from app.auth.email_delivery import EmailVerificationDelivery
from app.auth.registration import PendingWebUser, RegistrationService
from app.auth.registration_router import create_registration_router
from app.auth.rate_limit import AuthRateLimitService, RateLimitState


class RegistrationRepository:
    def __init__(self) -> None:
        self.token_hash = ""
        self.user = PendingWebUser("user-1", "profile-1", "reader@example.com")

    async def create_pending_user(self, **values: object) -> PendingWebUser:
        self.token_hash = str(values["verification_token_hash"])
        self.user = PendingWebUser("user-1", "profile-1", str(values["email_normalized"]))
        return self.user

    async def consume_email_verification_token(self, *, token_hash: str, now: datetime):
        return self.user if token_hash == self.token_hash else None


class RecordingDelivery(EmailVerificationDelivery):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_verification(self, *, email: str, token: str, expires_at: datetime) -> None:
        self.sent.append((email, token))


async def request(app: FastAPI, method: str, path: str, **kwargs: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def test_registration_sends_token_only_to_delivery_provider() -> None:
    repository = RegistrationRepository()
    delivery = RecordingDelivery()
    app = FastAPI()
    app.include_router(create_registration_router(RegistrationService(repository), delivery))

    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/register",
            json={
                "email": "reader@example.com",
                "display_name": "Reader",
                "password": "SafePassword!2026",
            },
        )
    )

    assert response.status_code == 202
    assert response.json() == {"status": "verification_pending"}
    assert delivery.sent[0][0] == "reader@example.com"
    assert delivery.sent[0][1] not in response.text


def test_email_verification_accepts_token_only_in_post_body() -> None:
    repository = RegistrationRepository()
    delivery = RecordingDelivery()
    app = FastAPI()
    app.include_router(create_registration_router(RegistrationService(repository), delivery))
    asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/register",
            json={
                "email": "reader@example.com",
                "display_name": "Reader",
                "password": "SafePassword!2026",
            },
        )
    )

    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/verify-email",
            json={"token": delivery.sent[0][1]},
        )
    )

    assert response.status_code == 200
    assert response.json() == {"status": "verified"}


def test_registration_returns_429_after_rate_limit_is_exhausted() -> None:
    class BlockingRateRepository:
        async def record_attempt(self, **values: object) -> RateLimitState:
            return RateLimitState(
                attempt_count=2,
                blocked_until=values["now"] + timedelta(minutes=1),  # type: ignore[operator]
            )

    app = FastAPI()
    app.include_router(
        create_registration_router(
            RegistrationService(RegistrationRepository()),
            RecordingDelivery(),
            AuthRateLimitService(BlockingRateRepository()),  # type: ignore[arg-type]
        )
    )

    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/auth/register",
            json={
                "email": "reader@example.com",
                "display_name": "Reader",
                "password": "SafePassword!2026",
            },
        )
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "try again later"


def test_verify_email_returns_429_after_global_attempt_limit_is_exhausted() -> None:
    from app.auth.rate_limit import InMemoryRateLimitRepository

    app = FastAPI()
    limiter = AuthRateLimitService(
        InMemoryRateLimitRepository(),
        limit=2,
        window=timedelta(minutes=10),
        block_duration=timedelta(minutes=30),
    )
    app.include_router(
        create_registration_router(
            RegistrationService(RegistrationRepository()),
            RecordingDelivery(),
            verify_rate_limiter=limiter,
        )
    )

    for _ in range(2):
        response = asyncio.run(
            request(app, "POST", "/api/v1/auth/verify-email", json={"token": "000000"})
        )
        assert response.status_code == 400

    blocked = asyncio.run(
        request(app, "POST", "/api/v1/auth/verify-email", json={"token": "000000"})
    )
    assert blocked.status_code == 429
