import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.rate_limit import (
    AuthRateLimitService,
    InMemoryRateLimitRepository,
    RateLimitError,
    RateLimitState,
)


class FakeRateLimitRepository:
    def __init__(self) -> None:
        self.count = 0
        self.subject_hashes: list[str] = []

    async def record_attempt(
        self,
        *,
        subject_kind: str,
        subject_hash: str,
        window_started_at: datetime,
        now: datetime,
        limit: int,
        blocked_until: datetime,
    ) -> RateLimitState:
        self.count += 1
        self.subject_hashes.append(subject_hash)
        return RateLimitState(
            attempt_count=self.count,
            blocked_until=blocked_until if self.count > limit else None,
        )


def test_rate_limiter_hashes_the_subject_before_persistence() -> None:
    repository = FakeRateLimitRepository()
    limiter = AuthRateLimitService(repository, limit=2, window=timedelta(minutes=10))

    asyncio.run(limiter.enforce(subject_kind="email", subject="Reader@example.com"))

    assert repository.subject_hashes[0] != "Reader@example.com"
    assert len(repository.subject_hashes[0]) == 64


def test_rate_limiter_uses_in_memory_fallback_without_repository() -> None:
    limiter = AuthRateLimitService(None, limit=2, window=timedelta(minutes=10))
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)

    asyncio.run(limiter.enforce(subject_kind="email", subject="a@example.com", now=now))
    asyncio.run(limiter.enforce(subject_kind="email", subject="a@example.com", now=now))
    with pytest.raises(RateLimitError):
        asyncio.run(limiter.enforce(subject_kind="email", subject="a@example.com", now=now))


def test_in_memory_rate_limit_repository_isolates_subjects_and_clears_after_window() -> None:
    repository = InMemoryRateLimitRepository()
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    blocked_until = now + timedelta(minutes=30)

    first = asyncio.run(
        repository.record_attempt(
            subject_kind="email",
            subject_hash="hash-a",
            window_started_at=now,
            now=now,
            limit=1,
            blocked_until=blocked_until,
        )
    )
    second = asyncio.run(
        repository.record_attempt(
            subject_kind="email",
            subject_hash="hash-a",
            window_started_at=now,
            now=now,
            limit=1,
            blocked_until=blocked_until,
        )
    )
    other = asyncio.run(
        repository.record_attempt(
            subject_kind="email",
            subject_hash="hash-b",
            window_started_at=now,
            now=now,
            limit=1,
            blocked_until=blocked_until,
        )
    )

    assert first.blocked_until is None
    assert second.blocked_until == blocked_until
    assert other.blocked_until is None

    after_block = blocked_until + timedelta(minutes=1)
    reset = asyncio.run(
        repository.record_attempt(
            subject_kind="email",
            subject_hash="hash-a",
            window_started_at=after_block,
            now=after_block,
            limit=1,
            blocked_until=after_block + timedelta(minutes=30),
        )
    )
    assert reset.blocked_until is None


def test_rate_limiter_blocks_after_the_configured_limit() -> None:
    repository = FakeRateLimitRepository()
    limiter = AuthRateLimitService(
        repository,
        limit=2,
        window=timedelta(minutes=10),
        block_duration=timedelta(minutes=30),
    )
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)

    asyncio.run(limiter.enforce(subject_kind="email", subject="reader@example.com", now=now))
    asyncio.run(limiter.enforce(subject_kind="email", subject="reader@example.com", now=now))
    with pytest.raises(RateLimitError, match="too many attempts"):
        asyncio.run(limiter.enforce(subject_kind="email", subject="reader@example.com", now=now))
