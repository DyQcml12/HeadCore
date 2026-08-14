import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.rate_limit import AuthRateLimitService, RateLimitError, RateLimitState


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
