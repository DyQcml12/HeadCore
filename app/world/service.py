from __future__ import annotations

import hashlib
import json

from app.world.cache import AsyncTTLCache
from app.world.contracts import (
    WorldAcquisitionResult,
    WorldObservationBatch,
    WorldQuery,
)
from app.world.errors import WorldSourceError, WorldSourceErrorCode
from app.world.registry import WorldSourceRegistry


class WorldAcquisitionService:
    def __init__(
        self,
        registry: WorldSourceRegistry,
        cache: AsyncTTLCache[WorldObservationBatch],
        *,
        max_ttl_seconds: int = 86400,
    ) -> None:
        if max_ttl_seconds <= 0:
            raise ValueError("max_ttl_seconds must be positive")
        self._registry = registry
        self._cache = cache
        self._max_ttl_seconds = max_ttl_seconds

    async def acquire(self, query: WorldQuery) -> WorldAcquisitionResult:
        adapter = self._registry.get(query.source_id, query.capability)
        definition = adapter.definition
        if not definition.enabled:
            raise WorldSourceError(WorldSourceErrorCode.SOURCE_DISABLED)
        if not definition.legal_approved:
            raise WorldSourceError(WorldSourceErrorCode.POLICY_DENIED)

        cache_key = build_world_cache_key(query)
        ttl_seconds = min(query.ttl_seconds, self._max_ttl_seconds)

        async def load() -> WorldObservationBatch:
            batch = await adapter.fetch(query)
            if batch.source_id != definition.source_id or batch.capability != query.capability:
                raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
            return batch

        loaded = await self._cache.get_or_load(
            cache_key,
            ttl_seconds=ttl_seconds,
            loader=load,
        )
        return WorldAcquisitionResult(
            batch=loaded.value,
            cache_hit=loaded.cache_hit,
            shared_request=loaded.shared_request,
            cache_key=cache_key,
        )


def build_world_cache_key(query: WorldQuery) -> str:
    canonical = json.dumps(
        {
            "source": query.source_id,
            "capability": query.capability.value,
            "parameters": sorted(query.parameters.items()),
            "partition": query.cache_partition,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"world:{query.source_id}:{query.capability.value}:{digest}"
