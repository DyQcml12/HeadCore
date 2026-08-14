from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from app.knowledge.models import MemoryRecord, MemoryState
from app.knowledge.semantic_memory import EmbeddingProvider


class SemanticMemoryOutboxOperation(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"


class SemanticMemoryOutboxState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    RETRY = "retry"


@dataclass(frozen=True)
class SemanticMemoryOutboxEvent:
    id: str
    memory_record_id: str
    profile_id: str
    operation: SemanticMemoryOutboxOperation
    state: SemanticMemoryOutboxState
    attempts: int
    created_at: datetime


class SemanticMemoryOutboxRepository(Protocol):
    async def claim_pending(
        self,
        *,
        worker_id: str,
        limit: int,
    ) -> tuple[SemanticMemoryOutboxEvent, ...]: ...

    async def get_record(self, record_id: str) -> MemoryRecord | None: ...

    async def mark_completed(self, event_id: str) -> None: ...

    async def reschedule(self, event_id: str, *, reason: str) -> None: ...


class SemanticMemoryIndexWriter(Protocol):
    async def upsert(
        self,
        *,
        record_id: str,
        profile_id: str,
        vector: tuple[float, ...],
        revision: str = "",
    ) -> None: ...

    async def remove(self, *, record_id: str) -> None: ...


class SemanticMemoryOutboxProcessor:
    def __init__(
        self,
        repository: SemanticMemoryOutboxRepository,
        *,
        index: SemanticMemoryIndexWriter,
        embedding_provider: EmbeddingProvider,
        worker_id: str,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("semantic memory worker_id is required")
        self._repository = repository
        self._index = index
        self._embedding_provider = embedding_provider
        self._worker_id = worker_id

    async def initialize_index(self) -> None:
        ensure_collection = getattr(self._index, "ensure_collection", None)
        if not callable(ensure_collection):
            return
        vector = await self._embedding_provider.embed("semantic memory initialization")
        await ensure_collection(vector_size=len(vector))

    async def process_once(self, *, limit: int = 32) -> int:
        if limit <= 0:
            return 0
        events = await self._repository.claim_pending(worker_id=self._worker_id, limit=limit)
        completed = 0
        for event in events:
            try:
                await self._apply(event)
                await self._repository.mark_completed(event.id)
                completed += 1
            except Exception as exc:
                await self._repository.reschedule(event.id, reason=_failure_reason(exc))
        return completed

    async def _apply(self, event: SemanticMemoryOutboxEvent) -> None:
        if event.operation is SemanticMemoryOutboxOperation.DELETE:
            await self._index.remove(record_id=event.memory_record_id)
            return
        record = await self._repository.get_record(event.memory_record_id)
        if not _record_is_indexable(record):
            await self._index.remove(record_id=event.memory_record_id)
            return
        assert record is not None
        vector = await self._embedding_provider.embed(f"{record.key}\n{record.value}")
        await self._index.upsert(
            record_id=record.id,
            profile_id=record.profile_id,
            vector=vector,
            revision=record.updated_at.isoformat(),
        )


def _record_is_indexable(record: MemoryRecord | None) -> bool:
    return bool(
        record is not None
        and record.state is MemoryState.ACTIVE
        and (record.expires_at is None or record.expires_at > datetime.now(UTC))
    )


def _failure_reason(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    return name[:64] or "semantic_sync_failed"
