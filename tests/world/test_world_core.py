from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.world.cache import AsyncTTLCache
from app.world.contracts import (
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldQuery,
    WorldSourceCapability,
    WorldSourceDefinition,
    WorldSourceKind,
)
from app.world.errors import WorldSourceError, WorldSourceErrorCode
from app.world.registry import WorldSourceRegistry
from app.world.service import WorldAcquisitionService, build_world_cache_key


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class FakeAdapter:
    def __init__(self, *, enabled: bool = True, legal_approved: bool = True) -> None:
        self.definition = WorldSourceDefinition(
            source_id="fake",
            kind=WorldSourceKind.API,
            capabilities=frozenset({WorldSourceCapability.NEWS}),
            enabled=enabled,
            legal_approved=legal_approved,
        )
        self.calls = 0

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch:
        self.calls += 1
        now = datetime.now(UTC)
        evidence = WorldEvidence(
            source_id="fake",
            source_uri="https://example.test/news",
            retrieved_at=now,
            content_hash="a" * 64,
        )
        observation = WorldObservation(
            observation_id=f"fake:{self.calls}",
            capability=query.capability,
            observed_at=now,
            expires_at=now + timedelta(seconds=query.ttl_seconds),
            confidence=0.8,
            payload={"title": "test"},
            evidence=(evidence,),
        )
        return WorldObservationBatch(
            source_id="fake",
            capability=query.capability,
            fetched_at=now,
            observations=(observation,),
        )


def test_query_rejects_credentials_in_parameters() -> None:
    with pytest.raises(ValueError, match="credentials"):
        WorldQuery(
            source_id="fake",
            capability=WorldSourceCapability.NEWS,
            parameters={"api_key": "must-not-be-here"},
        )


def test_cache_key_hashes_private_query_values() -> None:
    ip = "8.8.8.8"
    key = build_world_cache_key(
        WorldQuery(
            source_id="amap",
            capability=WorldSourceCapability.IP_LOCATION,
            parameters={"ip": ip},
            cache_partition="coarse-location",
        )
    )
    assert ip not in key
    assert len(key.rsplit(":", 1)[-1]) == 64


def test_registry_rejects_duplicate_source() -> None:
    registry = WorldSourceRegistry()
    registry.register(FakeAdapter())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeAdapter())


def test_service_denies_source_without_legal_approval() -> None:
    async def scenario() -> None:
        registry = WorldSourceRegistry()
        registry.register(FakeAdapter(legal_approved=False))
        service = WorldAcquisitionService(registry, AsyncTTLCache())
        with pytest.raises(WorldSourceError) as captured:
            await service.acquire(
                WorldQuery(source_id="fake", capability=WorldSourceCapability.NEWS)
            )
        assert captured.value.code == WorldSourceErrorCode.POLICY_DENIED

    asyncio.run(scenario())


def test_service_reuses_cached_batch_until_ttl_expires() -> None:
    async def scenario() -> None:
        clock = FakeClock()
        adapter = FakeAdapter()
        registry = WorldSourceRegistry()
        registry.register(adapter)
        service = WorldAcquisitionService(
            registry,
            AsyncTTLCache(clock=clock),
        )
        query = WorldQuery(
            source_id="fake",
            capability=WorldSourceCapability.NEWS,
            ttl_seconds=30,
        )
        first = await service.acquire(query)
        second = await service.acquire(query)
        clock.value += 31
        third = await service.acquire(query)

        assert first.cache_hit is False
        assert second.cache_hit is True
        assert third.cache_hit is False
        assert adapter.calls == 2

    asyncio.run(scenario())


def test_cache_coalesces_concurrent_loads() -> None:
    async def scenario() -> None:
        cache: AsyncTTLCache[str] = AsyncTTLCache()
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def loader() -> str:
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return "shared"

        first_task = asyncio.create_task(
            cache.get_or_load("one", ttl_seconds=30, loader=loader)
        )
        await started.wait()
        second_task = asyncio.create_task(
            cache.get_or_load("one", ttl_seconds=30, loader=loader)
        )
        await asyncio.sleep(0)
        release.set()
        first, second = await asyncio.gather(first_task, second_task)

        assert calls == 1
        assert first.value == second.value == "shared"
        assert {first.shared_request, second.shared_request} == {False, True}

    asyncio.run(scenario())
