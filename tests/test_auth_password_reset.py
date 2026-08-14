from __future__ import annotations

import asyncio
import importlib
import importlib.util
from datetime import datetime, timezone

from app.auth.passwords import hash_password, verify_password
from app.auth.service import WebUser
from app.auth.sessions import hash_opaque_token


class ResetRepository:
    def __init__(self) -> None:
        self.user = WebUser(
            id="user-1",
            profile_id="profile-1",
            email_normalized="reader@example.com",
            password_hash=hash_password("SafePassword!2026"),
            status="active",
        )
        self.issued_token_hash: str | None = None
        self.password_hash: str | None = None
        self.revoked_user_id: str | None = None

    async def find_user_by_email(self, *, email_normalized: str) -> WebUser | None:
        return self.user if email_normalized == self.user.email_normalized else None

    async def create_password_reset_token(self, **values: object) -> None:
        self.issued_token_hash = str(values["token_hash"])

    async def consume_password_reset_token(
        self,
        *,
        token_hash: str,
        password_hash: str,
        now: datetime,
    ) -> WebUser | None:
        if token_hash != self.issued_token_hash:
            return None
        self.password_hash = password_hash
        self.revoked_user_id = self.user.id
        return self.user


class ResetDelivery:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_password_reset(self, *, email: str, token: str, expires_at: datetime) -> None:
        self.sent.append((email, token))


def password_reset_module():
    spec = importlib.util.find_spec("app.auth.password_reset")
    assert spec is not None, "password reset service must be provided"
    return importlib.import_module("app.auth.password_reset")


def test_password_reset_persists_only_a_token_hash_and_revokes_sessions() -> None:
    module = password_reset_module()
    repository = ResetRepository()
    delivery = ResetDelivery()
    service = module.PasswordResetService(repository, delivery)
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    asyncio.run(service.request(email="reader@example.com", now=now))

    assert delivery.sent[0][0] == "reader@example.com"
    raw_token = delivery.sent[0][1]
    assert repository.issued_token_hash == hash_opaque_token(raw_token)
    assert repository.issued_token_hash != raw_token

    asyncio.run(service.confirm(token=raw_token, password="ChangedPassword!2026", now=now))

    assert repository.password_hash is not None
    assert verify_password(repository.password_hash, "ChangedPassword!2026") is True
    assert repository.revoked_user_id == "user-1"


def test_password_reset_request_returns_the_same_result_for_unknown_email() -> None:
    module = password_reset_module()
    repository = ResetRepository()
    delivery = ResetDelivery()
    service = module.PasswordResetService(repository, delivery)
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    known = asyncio.run(service.request(email="reader@example.com", now=now))
    unknown = asyncio.run(service.request(email="missing@example.com", now=now))

    assert known is None
    assert unknown is None
    assert len(delivery.sent) == 1
