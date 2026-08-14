from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from secrets import token_urlsafe
from threading import Lock
from uuid import uuid4

from app.auth.sessions import hash_opaque_token, session_is_active


class WorkbenchUnavailableError(Exception):
    pass


class WorkbenchAuthenticationError(Exception):
    pass


class WorkbenchCsrfError(Exception):
    pass


class WorkbenchRateLimitError(Exception):
    pass


@dataclass(frozen=True)
class WorkbenchIdentity:
    session_id: str
    expires_at: datetime

    @property
    def owner_key(self) -> str:
        return f"workbench:{self.session_id}"


@dataclass(frozen=True)
class WorkbenchLogin:
    session_token: str
    csrf_token: str
    identity: WorkbenchIdentity


@dataclass(frozen=True)
class _StoredWorkbenchSession:
    identity: WorkbenchIdentity
    csrf_secret_hash: str


@dataclass(frozen=True)
class _LoginFailureState:
    attempts: tuple[datetime, ...]
    blocked_until: datetime | None


class WorkbenchSessionStore:
    """In-memory local-admin sessions. Raw cookies are never retained server-side."""

    def __init__(
        self,
        *,
        enabled: bool,
        admin_secret: str,
        lifetime_seconds: int,
    ) -> None:
        if lifetime_seconds < 300 or lifetime_seconds > 28_800:
            raise ValueError("workbench session lifetime must be between 300 and 28800 seconds")
        self._enabled = enabled
        self._admin_secret = admin_secret
        self._lifetime = timedelta(seconds=lifetime_seconds)
        self._sessions: dict[str, _StoredWorkbenchSession] = {}
        self._login_failures: dict[str, _LoginFailureState] = {}
        self._lock = Lock()

    @property
    def available(self) -> bool:
        return self._enabled and bool(self._admin_secret)

    def login(
        self,
        *,
        supplied_secret: str,
        subject: str,
        now: datetime | None = None,
    ) -> WorkbenchLogin:
        self._require_available()
        timestamp = now or datetime.now(UTC)
        with self._lock:
            self._purge_expired(timestamp)
            failure_state = self._login_failures.get(subject)
            if failure_state and failure_state.blocked_until and timestamp < failure_state.blocked_until:
                raise WorkbenchRateLimitError("try again later")
            if not compare_digest(self._admin_secret, supplied_secret):
                attempts = tuple(
                    attempt
                    for attempt in (failure_state.attempts if failure_state else ())
                    if timestamp - attempt < timedelta(minutes=10)
                ) + (timestamp,)
                blocked_until = timestamp + timedelta(minutes=15) if len(attempts) >= 5 else None
                self._login_failures[subject] = _LoginFailureState(
                    attempts=attempts,
                    blocked_until=blocked_until,
                )
                raise WorkbenchAuthenticationError("invalid administrator secret")
            self._login_failures.pop(subject, None)
            identity = WorkbenchIdentity(
                session_id=f"wb_{uuid4().hex}",
                expires_at=timestamp + self._lifetime,
            )
            session_token = token_urlsafe(32)
            csrf_token = token_urlsafe(32)
            self._sessions[hash_opaque_token(session_token)] = _StoredWorkbenchSession(
                identity=identity,
                csrf_secret_hash=hash_opaque_token(csrf_token),
            )
        return WorkbenchLogin(
            session_token=session_token,
            csrf_token=csrf_token,
            identity=identity,
        )

    def require(
        self,
        *,
        session_token: str | None,
        csrf_token: str | None = None,
        require_csrf: bool = False,
        now: datetime | None = None,
    ) -> WorkbenchIdentity:
        self._require_available()
        if not session_token:
            raise WorkbenchAuthenticationError("authentication required")
        timestamp = now or datetime.now(UTC)
        with self._lock:
            self._purge_expired(timestamp)
            stored = self._sessions.get(hash_opaque_token(session_token))
        if stored is None or not session_is_active(
            expires_at=stored.identity.expires_at,
            revoked_at=None,
            now=timestamp,
        ):
            raise WorkbenchAuthenticationError("authentication required")
        if require_csrf and (
            not csrf_token
            or not compare_digest(hash_opaque_token(csrf_token), stored.csrf_secret_hash)
        ):
            raise WorkbenchCsrfError("csrf validation failed")
        return stored.identity

    def logout(self, *, session_token: str | None, now: datetime | None = None) -> WorkbenchIdentity:
        identity = self.require(session_token=session_token, now=now)
        assert session_token is not None
        with self._lock:
            self._sessions.pop(hash_opaque_token(session_token), None)
        return identity

    def _require_available(self) -> None:
        if not self.available:
            raise WorkbenchUnavailableError("visual workbench is unavailable")

    def _purge_expired(self, now: datetime) -> None:
        expired = [
            token_hash
            for token_hash, stored in self._sessions.items()
            if not session_is_active(
                expires_at=stored.identity.expires_at,
                revoked_at=None,
                now=now,
            )
        ]
        for token_hash in expired:
            self._sessions.pop(token_hash, None)
        expired_failure_subjects = [
            subject
            for subject, failure_state in self._login_failures.items()
            if failure_state.blocked_until is not None and failure_state.blocked_until <= now
        ]
        for subject in expired_failure_subjects:
            self._login_failures.pop(subject, None)
