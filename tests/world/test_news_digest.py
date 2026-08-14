from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.world.contracts import (
    WorldAcquisitionResult,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldSourceCapability,
)
from app.world.errors import WorldSourceError, WorldSourceErrorCode
from app.world.news_digest import NewsDigestService


class FakeNewsAcquirer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def news(self, source_id: str, *, topic: str = "", limit: int = 20):  # type: ignore[no-untyped-def]
        self.calls.append(source_id)
        if source_id == "broken":
            raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE)
        items = (
            [
                {
                    "title": "Shared policy update",
                    "url": "https://one.example/policy",
                    "published_at": "2026-07-17T08:00:00+00:00",
                    "summary": "short",
                    "source_name": "One",
                    "source_country": "China",
                    "language": "zh-CN",
                },
                {
                    "title": "Older item",
                    "url": "https://one.example/older",
                    "published_at": "2026-07-16T08:00:00+00:00",
                    "summary": "",
                    "source_name": "One",
                    "source_country": "China",
                    "language": "zh-CN",
                },
            ]
            if source_id == "one"
            else [
                {
                    "title": "Shared policy update",
                    "url": "https://two.example/policy",
                    "published_at": "2026-07-17T09:00:00+00:00",
                    "summary": "a longer shared summary",
                    "source_name": "Two",
                    "source_country": "United Kingdom",
                    "language": "English",
                }
            ]
        )
        now = datetime.now(UTC)
        evidence = WorldEvidence(
            source_id=source_id,
            source_uri=f"https://{source_id}.example/feed",
            retrieved_at=now,
            content_hash=source_id * 16,
        )
        observation = WorldObservation(
            observation_id=f"{source_id}:news",
            capability=WorldSourceCapability.NEWS,
            observed_at=now,
            expires_at=now + timedelta(minutes=5),
            confidence=0.8,
            payload={"topic": topic, "items": items[:limit]},
            evidence=(evidence,),
        )
        batch = WorldObservationBatch(
            source_id=source_id,
            capability=WorldSourceCapability.NEWS,
            fetched_at=now,
            observations=(observation,),
        )
        return WorldAcquisitionResult(
            batch=batch,
            cache_hit=False,
            shared_request=False,
            cache_key=f"source:{source_id}",
        )


def test_digest_merges_duplicate_titles_and_preserves_all_sources() -> None:
    async def scenario() -> None:
        acquirer = FakeNewsAcquirer()
        service = NewsDigestService(acquirer)
        result = await service.build(
            topic="policy",
            source_ids=("two", "one", "broken"),
        )

        assert len(result.digest.items) == 2
        shared = result.digest.items[0]
        assert shared.title == "Shared policy update"
        assert shared.urls == (
            "https://one.example/policy",
            "https://two.example/policy",
        )
        assert shared.source_ids == ("one", "two")
        assert shared.summary == "a longer shared summary"
        assert shared.published_at == "2026-07-17T09:00:00+00:00"
        assert next(source for source in result.digest.sources if source.source_id == "broken").error_code == "unavailable"
        assert "policy" not in result.cache_key

    asyncio.run(scenario())


def test_digest_cache_reuses_first_users_result() -> None:
    async def scenario() -> None:
        acquirer = FakeNewsAcquirer()
        service = NewsDigestService(acquirer)

        first = await service.build(topic="health", source_ids=("one", "two"))
        second = await service.build(topic="health", source_ids=("two", "one"))

        assert first.cache_hit is False
        assert second.cache_hit is True
        assert acquirer.calls == ["one", "two"]

    asyncio.run(scenario())
