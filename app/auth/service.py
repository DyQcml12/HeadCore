from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from secrets import token_urlsafe
from typing import Protocol

from app.auth.audit import AuthAuditEvent, AuthAuditSink
from app.auth.passwords import verify_password
from app.auth.sessions import hash_opaque_token, issue_session, session_is_active


class AuthenticationError(Exception):
    pass


@dataclass(frozen=True)
class WebUser:
    id: str
    profile_id: str
    email_normalized: str
    password_hash: str
    status: str


@dataclass(frozen=True)
class StoredSession:
    id: str
    user_id: str
    profile_id: str
    token_hash: str
    csrf_secret_hash: str
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class AccountProfile:
    user_id: str
    profile_id: str
    display_name: str
    email_normalized: str
    email_verified: bool
    created_at: datetime


@dataclass(frozen=True)
class AuthenticatedAccount:
    profile: AccountProfile
    session_expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    session_id: str
    user_id: str
    profile_id: str
    expires_at: datetime
    session_token: str
    csrf_token: str


class AuthRepository(Protocol):
    async def find_user_by_email(self, *, email_normalized: str) -> WebUser | None: ...

    async def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        csrf_secret_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> StoredSession: ...

    async def find_session_by_token_hash(self, *, token_hash: str) -> StoredSession | None: ...

    async def find_account_by_user_id(self, *, user_id: str) -> AccountProfile | None: ...

    async def revoke_session(self, *, session_id: str, revoked_at: datetime) -> None: ...


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        session_lifetime: timedelta = timedelta(days=7),
        audit_sink: AuthAuditSink | None = None,
    ) -> None:
        self._repository = repository
        self._session_lifetime = session_lifetime
        self._audit_sink = audit_sink

    async def login(self, *, email: str, password: str, now: datetime | None = None) -> AuthenticatedSession:
        timestamp = now or datetime.now(timezone.utc)
        email_normalized = normalize_email(email)
        user = await self._repository.find_user_by_email(email_normalized=email_normalized)
        if user is None or user.status != "active" or not verify_password(user.password_hash, password):
            await self._audit("login_attempt", "rejected", "invalid_credentials", user.id if user else None)
            raise AuthenticationError("invalid email or password")
        issued = issue_session(now=timestamp, lifetime=self._session_lifetime)
        csrf_token = token_urlsafe(32)
        stored = await self._repository.create_session(
            user_id=user.id,
            token_hash=issued.token_hash,
            csrf_secret_hash=hash_opaque_token(csrf_token),
            expires_at=issued.expires_at,
            created_at=timestamp,
        )
        await self._audit("login_succeeded", "accepted", "session_created", user.id)
        return AuthenticatedSession(
            session_id=stored.id,
            user_id=user.id,
            profile_id=user.profile_id,
            expires_at=issued.expires_at,
            session_token=issued.token,
            csrf_token=csrf_token,
        )

    async def require_session(
        self,
        *,
        session_token: str | None,
        csrf_token: str | None = None,
        require_csrf: bool = False,
        now: datetime | None = None,
    ) -> StoredSession:
        if not session_token:
            raise AuthenticationError("authentication required")
        session = await self._repository.find_session_by_token_hash(
            token_hash=hash_opaque_token(session_token)
        )
        timestamp = now or datetime.now(timezone.utc)
        if session is None or not session_is_active(
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            now=timestamp,
        ):
            raise AuthenticationError("authentication required")
        if require_csrf:
            if not csrf_token or not compare_digest(
                hash_opaque_token(csrf_token), session.csrf_secret_hash
            ):
                raise AuthenticationError("csrf validation failed")
        return session

    async def logout(self, *, session_token: str | None, now: datetime | None = None) -> None:
        session = await self.require_session(session_token=session_token, now=now)
        await self._repository.revoke_session(
            session_id=session.id,
            revoked_at=now or datetime.now(timezone.utc),
        )
        await self._audit("logout", "accepted", "session_revoked", session.user_id)

    async def current_account(
        self,
        *,
        session_token: str | None,
        now: datetime | None = None,
    ) -> AuthenticatedAccount:
        session = await self.require_session(session_token=session_token, now=now)
        profile = await self._repository.find_account_by_user_id(user_id=session.user_id)
        if profile is None:
            raise AuthenticationError("authentication required")
        return AuthenticatedAccount(profile=profile, session_expires_at=session.expires_at)

    async def _audit(
        self,
        event_type: str,
        outcome: str,
        reason_code: str,
        user_id: str | None,
    ) -> None:
        if self._audit_sink is not None:
            await self._audit_sink.record(
                AuthAuditEvent(
                    event_type=event_type,
                    outcome=outcome,  # type: ignore[arg-type]
                    reason_code=reason_code,
                    user_id=user_id,
                )
            )


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    local, separator, domain = email.partition("@")
    if (
        not separator
        or not local
        or not domain
        or "." not in domain
        or len(email) > 320
        or any(character.isspace() for character in email)
    ):
        raise AuthenticationError("invalid email or password")
    return email
