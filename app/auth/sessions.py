from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe


@dataclass(frozen=True)
class IssuedSession:
    """The raw value is returned once for a HttpOnly cookie; storage gets only its hash."""

    token: str
    token_hash: str
    expires_at: datetime


def hash_opaque_token(token: str) -> str:
    if not token:
        raise ValueError("opaque token must not be empty")
    return sha256(token.encode("utf-8")).hexdigest()


def issue_session(*, now: datetime | None = None, lifetime: timedelta = timedelta(days=7)) -> IssuedSession:
    if lifetime <= timedelta(0):
        raise ValueError("session lifetime must be positive")
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        raise ValueError("session issuance time must be timezone-aware")
    token = token_urlsafe(32)
    return IssuedSession(
        token=token,
        token_hash=hash_opaque_token(token),
        expires_at=issued_at + lifetime,
    )


def session_is_active(*, expires_at: datetime, revoked_at: datetime | None, now: datetime) -> bool:
    if expires_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("session times must be timezone-aware")
    return revoked_at is None and expires_at > now
