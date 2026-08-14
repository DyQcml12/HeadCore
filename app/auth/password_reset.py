from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.auth.codes import new_six_digit_code

from app.auth.audit import AuthAuditEvent, AuthAuditSink
from app.auth.passwords import PasswordPolicyError, hash_password
from app.auth.service import AuthenticationError, WebUser, normalize_email
from app.auth.sessions import hash_opaque_token


class PasswordResetError(Exception):
    pass


class PasswordResetRepository(Protocol):
    async def find_user_by_email(self, *, email_normalized: str) -> WebUser | None: ...

    async def create_password_reset_token(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> None: ...

    async def consume_password_reset_token(
        self,
        *,
        token_hash: str,
        password_hash: str,
        now: datetime,
    ) -> WebUser | None: ...


class PasswordResetDelivery(Protocol):
    async def send_password_reset(self, *, email: str, token: str, expires_at: datetime) -> None: ...


class PasswordResetService:
    def __init__(
        self,
        repository: PasswordResetRepository,
        delivery: PasswordResetDelivery,
        *,
        token_lifetime: timedelta = timedelta(minutes=30),
        audit_sink: AuthAuditSink | None = None,
    ) -> None:
        if token_lifetime <= timedelta(0):
            raise ValueError("password reset token lifetime must be positive")
        self._repository = repository
        self._delivery = delivery
        self._token_lifetime = token_lifetime
        self._audit_sink = audit_sink

    async def request(self, *, email: str, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(timezone.utc)
        try:
            email_normalized = normalize_email(email)
        except AuthenticationError:
            return
        user = await self._repository.find_user_by_email(email_normalized=email_normalized)
        if user is None or user.status != "active":
            await self._audit("password_reset_requested", "accepted", "generic_response", None)
            return
        token = new_six_digit_code()
        expires_at = timestamp + self._token_lifetime
        await self._repository.create_password_reset_token(
            user_id=user.id,
            token_hash=hash_opaque_token(token),
            expires_at=expires_at,
            created_at=timestamp,
        )
        try:
            await self._delivery.send_password_reset(
                email=user.email_normalized,
                token=token,
                expires_at=expires_at,
            )
        except Exception:
            await self._audit("password_reset_requested", "failed", "delivery_failed", user.id)
            return
        await self._audit("password_reset_requested", "accepted", "token_sent", user.id)

    async def confirm(
        self,
        *,
        token: str,
        password: str,
        now: datetime | None = None,
    ) -> None:
        if not token.strip():
            raise PasswordResetError("invalid or expired reset token")
        try:
            password_hash = hash_password(password)
        except PasswordPolicyError as exc:
            raise PasswordResetError(str(exc)) from exc
        user = await self._repository.consume_password_reset_token(
            token_hash=hash_opaque_token(token),
            password_hash=password_hash,
            now=now or datetime.now(timezone.utc),
        )
        if user is None:
            await self._audit("password_reset_completed", "rejected", "invalid_or_expired_token", None)
            raise PasswordResetError("invalid or expired reset token")
        await self._audit("password_reset_completed", "accepted", "password_updated", user.id)

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
