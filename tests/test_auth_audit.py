import asyncio

import pytest

from app.auth.audit import AuthAuditEvent, AuthAuditSink
from app.auth.passwords import hash_password
from app.auth.service import AuthService, AuthenticationError, StoredSession, WebUser


class FakeAuditSink(AuthAuditSink):
    def __init__(self) -> None:
        self.events: list[AuthAuditEvent] = []

    async def record(self, event: AuthAuditEvent) -> None:
        self.events.append(event)


class FakeRepository:
    async def find_user_by_email(self, *, email_normalized: str) -> WebUser | None:
        return WebUser(
            id="user-1",
            profile_id="profile-1",
            email_normalized=email_normalized,
            password_hash=hash_password("SafePassword!2026"),
            status="active",
        )

    async def create_session(self, **values: object) -> StoredSession:
        return StoredSession(
            id="session-1",
            user_id="user-1",
            profile_id="profile-1",
            token_hash=str(values["token_hash"]),
            csrf_secret_hash=str(values["csrf_secret_hash"]),
            expires_at=values["expires_at"],  # type: ignore[arg-type]
            revoked_at=None,
        )

    async def find_session_by_token_hash(self, *, token_hash: str) -> StoredSession | None:
        return None

    async def revoke_session(self, *, session_id: str, revoked_at) -> None:
        return None


def test_login_audit_records_outcome_without_password_or_token() -> None:
    sink = FakeAuditSink()
    service = AuthService(FakeRepository(), audit_sink=sink)

    asyncio.run(service.login(email="reader@example.com", password="SafePassword!2026"))
    with pytest.raises(AuthenticationError):
        asyncio.run(service.login(email="reader@example.com", password="wrong"))

    assert [(event.event_type, event.outcome) for event in sink.events] == [
        ("login_succeeded", "accepted"),
        ("login_attempt", "rejected"),
    ]
    assert all("SafePassword" not in str(event) and "wrong" not in str(event) for event in sink.events)
