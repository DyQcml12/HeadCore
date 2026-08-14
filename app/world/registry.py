from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.world.contracts import (
    WorldObservationBatch,
    WorldQuery,
    WorldSourceCapability,
    WorldSourceDefinition,
)
from app.world.errors import WorldSourceError, WorldSourceErrorCode


@runtime_checkable
class WorldSourceAdapter(Protocol):
    definition: WorldSourceDefinition

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch: ...


class WorldSourceRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, WorldSourceAdapter] = {}

    def register(self, adapter: WorldSourceAdapter) -> None:
        source_id = adapter.definition.source_id
        if source_id in self._adapters:
            raise ValueError(f"world source already registered: {source_id}")
        self._adapters[source_id] = adapter

    def get(
        self,
        source_id: str,
        capability: WorldSourceCapability,
    ) -> WorldSourceAdapter:
        normalized = source_id.strip().lower()
        adapter = self._adapters.get(normalized)
        if adapter is None:
            raise WorldSourceError(WorldSourceErrorCode.SOURCE_NOT_FOUND)
        if capability not in adapter.definition.capabilities:
            raise WorldSourceError(WorldSourceErrorCode.CAPABILITY_UNSUPPORTED)
        return adapter

    def definitions(self) -> tuple[WorldSourceDefinition, ...]:
        return tuple(
            self._adapters[source_id].definition for source_id in sorted(self._adapters)
        )
