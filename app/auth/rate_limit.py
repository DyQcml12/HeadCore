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


class AuthRateLimitService:
    def __init__(
        self,
        repository: RateLimitRepository,
        *,
        limit: int = 5,
        window: timedelta = timedelta(minutes=10),
        block_duration: timedelta = timedelta(minutes=30),
    ) -> None:
        if limit < 1 or window <= timedelta(0) or block_duration <= timedelta(0):
            raise ValueError("rate limit policy must be positive")
        self._repository = repository
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
