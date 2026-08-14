from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.auth.codes import new_six_digit_code
from app.auth.passwords import PasswordPolicyError, hash_password
from app.auth.service import normalize_email
from app.auth.sessions import hash_opaque_token


class RegistrationError(Exception):
    pass


@dataclass(frozen=True)
class PendingWebUser:
    id: str
    profile_id: str
    email_normalized: str


@dataclass(frozen=True)
class RegistrationResult:
    user_id: str
    profile_id: str
    email_normalized: str
    verification_token: str
    verification_expires_at: datetime


class RegistrationRepository(Protocol):
    async def create_pending_user(
        self,
        *,
        email_normalized: str,
        display_name: str,
        password_hash: str,
        verification_token_hash: str,
        verification_expires_at: datetime,
        created_at: datetime,
    ) -> PendingWebUser: ...

    async def consume_email_verification_token(
        self, *, token_hash: str, now: datetime
    ) -> PendingWebUser | None: ...


class RegistrationService:
    def __init__(
        self,
        repository: RegistrationRepository,
        *,
        verification_lifetime: timedelta = timedelta(minutes=30),
    ) -> None:
        if verification_lifetime <= timedelta(0):
            raise ValueError("verification lifetime must be positive")
        self._repository = repository
        self._verification_lifetime = verification_lifetime

    async def register(
        self,
        *,
        email: str,
        display_name: str,
        password: str,
        now: datetime | None = None,
    ) -> RegistrationResult:
        timestamp = now or datetime.now(timezone.utc)
        clean_display_name = display_name.strip()
        if not clean_display_name or len(clean_display_name) > 128:
            raise RegistrationError("invalid registration data")
        try:
            email_normalized = normalize_email(email)
        except Exception as exc:
            raise RegistrationError("invalid registration data") from exc
        verification_token = new_six_digit_code()
        expires_at = timestamp + self._verification_lifetime
        try:
            password_hash = hash_password(password)
        except PasswordPolicyError as exc:
            raise RegistrationError(str(exc)) from exc
        except Exception as exc:
            raise RegistrationError("invalid registration data") from exc
        user = await self._repository.create_pending_user(
            email_normalized=email_normalized,
            display_name=clean_display_name,
            password_hash=password_hash,
            verification_token_hash=hash_opaque_token(verification_token),
            verification_expires_at=expires_at,
            created_at=timestamp,
        )
        return RegistrationResult(
            user_id=user.id,
            profile_id=user.profile_id,
            email_normalized=user.email_normalized,
            verification_token=verification_token,
            verification_expires_at=expires_at,
        )

    async def verify_email(self, *, token: str, now: datetime | None = None) -> PendingWebUser:
        if not token:
            raise RegistrationError("invalid or expired verification token")
        user = await self._repository.consume_email_verification_token(
            token_hash=hash_opaque_token(token),
            now=now or datetime.now(timezone.utc),
        )
        if user is None:
            raise RegistrationError("invalid or expired verification token")
        return user
