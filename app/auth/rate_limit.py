from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal, Protocol


RateLimitSubjectKind = Literal["email", "ip_prefix", "device"]


class RateLimitError(Exception):
    pass


@dataclass(frozen=True)
class RateLimitState:
    attempt_count: int
    blocked_until: datetime | None


class RateLimitRepository(Protocol):
    async def record_attempt(
        self,
        *,
        subject_kind: RateLimitSubjectKind,
        subject_hash: str,
        window_started_at: datetime,
        now: datetime,
        limit: int,
        blocked_until: datetime,
    ) -> RateLimitState: ...


class InMemoryRateLimitRepository:
    """Single-process rate limit fallback and test double.

    Used when no database repository is available (or in tests). State is
    process-local: it is NOT a shared limiter for multi-instance deployments,
    which must provide a database or Redis-backed repository instead.
    """

    def __init__(self, *, max_entries: int = 10_000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._attempts: dict[tuple[str, str], dict[str, int]] = {}
        self._blocked_until: dict[tuple[str, str], datetime] = {}

    async def record_attempt(
        self,
        *,
        subject_kind: RateLimitSubjectKind,
        subject_hash: str,
        window_started_at: datetime,
        now: datetime,
        limit: int,
        blocked_until: datetime,
    ) -> RateLimitState:
        self._purge_expired(now)
        key = (subject_kind, subject_hash)
        window_key = window_started_at.isoformat()
        windows = self._attempts.setdefault(key, {})
        if windows.get(window_key) is None:
            windows.clear()
        count = windows.get(window_key, 0) + 1
        windows[window_key] = count
        if len(self._attempts) > self._max_entries:
            self._attempts.pop(next(iter(self._attempts)))
        existing_block = self._blocked_until.get(key)
        if existing_block is not None and existing_block > now:
            return RateLimitState(attempt_count=count, blocked_until=existing_block)
        if count > limit:
            self._blocked_until[key] = blocked_until
            return RateLimitState(attempt_count=count, blocked_until=blocked_until)
        return RateLimitState(attempt_count=count, blocked_until=None)

    def _purge_expired(self, now: datetime) -> None:
        expired_blocks = [key for key, value in self._blocked_until.items() if value <= now]
        for key in expired_blocks:
            self._blocked_until.pop(key, None)
            self._attempts.pop(key, None)


class AuthRateLimitService:
    def __init__(
        self,
        repository: RateLimitRepository | None = None,
        *,
        limit: int = 5,
        window: timedelta = timedelta(minutes=10),
        block_duration: timedelta = timedelta(minutes=30),
    ) -> None:
        if limit < 1 or window <= timedelta(0) or block_duration <= timedelta(0):
            raise ValueError("rate limit policy must be positive")
        self._repository = repository or InMemoryRateLimitRepository()
        self._limit = limit
        self._window = window
        self._block_duration = block_duration

    async def enforce(
        self,
        *,
        subject_kind: RateLimitSubjectKind,
        subject: str,
        now: datetime | None = None,
    ) -> None:
        timestamp = now or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or not subject.strip():
            raise ValueError("rate limit input is invalid")
        window_started_at = _window_start(timestamp, self._window)
        state = await self._repository.record_attempt(
            subject_kind=subject_kind,
            subject_hash=sha256(subject.strip().lower().encode("utf-8")).hexdigest(),
            window_started_at=window_started_at,
            now=timestamp,
            limit=self._limit,
            blocked_until=timestamp + self._block_duration,
        )
        if state.blocked_until is not None and state.blocked_until > timestamp:
            raise RateLimitError("too many attempts")


def _window_start(timestamp: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=timezone.utc)
