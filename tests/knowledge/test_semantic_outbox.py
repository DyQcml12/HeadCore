from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from app.knowledge.models import MemoryRecord, MemoryScope, MemoryState
from app.knowledge.semantic_memory import InMemorySemanticMemoryIndex
from app.knowledge.semantic_outbox import (
    SemanticMemoryOutboxEvent,
    SemanticMemoryOutboxOperation,
    SemanticMemoryOutboxProcessor,
    SemanticMemoryOutboxState,
)


class MappingEmbeddingProvider:
    async def embed(self, text: str) -> tuple[float, ...]:
        assert text == "reply_preference\n技术问题希望分步骤回答。"
        return (0.8, 0.6)


class InMemoryOutboxRepository:
    def __init__(
        self,
        *,
        event: SemanticMemoryOutboxEvent,
        record: MemoryRecord,
    ) -> None:
        self.event = event
        self.record = record
        self.completed_ids: list[str] = []
        self.rescheduled: list[tuple[str, str]] = []

    async def claim_pending(self, *, worker_id: str, limit: int) -> tuple[SemanticMemoryOutboxEvent, ...]:
        assert worker_id == "semantic-test-worker"
        assert limit == 8
        if self.event.state is SemanticMemoryOutboxState.PENDING:
            self.event = SemanticMemoryOutboxEvent(
                id=self.event.id,
                memory_record_id=self.event.memory_record_id,
                profile_id=self.event.profile_id,
                operation=self.event.operation,
                state=SemanticMemoryOutboxState.PROCESSING,
                attempts=1,
                created_at=self.event.created_at,
            )
            return (self.event,)
        return ()

    async def get_record(self, record_id: str) -> MemoryRecord | None:
        assert record_id == self.record.id
        return self.record

    async def mark_completed(self, event_id: str) -> None:
        self.completed_ids.append(event_id)

    async def reschedule(self, event_id: str, *, reason: str) -> None:
        self.rescheduled.append((event_id, reason))


def _record(state: MemoryState = MemoryState.ACTIVE) -> MemoryRecord:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    return MemoryRecord(
        id="memory-preference",
        candidate_id="candidate-preference",
        profile_id="profile-a",
        key="reply_preference",
        value="技术问题希望分步骤回答。",
        scope=MemoryScope.PROFILE_PRIVATE,
        source_type="user_statement",
        source_id="message-preference",
        confidence=0.9,
        state=state,
        created_at=now,
        updated_at=now,
    )


def _event(operation: SemanticMemoryOutboxOperation) -> SemanticMemoryOutboxEvent:
    return SemanticMemoryOutboxEvent(
        id="event-preference",
        memory_record_id="memory-preference",
        profile_id="profile-a",
        operation=operation,
        state=SemanticMemoryOutboxState.PENDING,
        attempts=0,
        created_at=datetime(2026, 8, 2, tzinfo=UTC),
    )


def test_outbox_processor_indexes_only_active_authoritative_memory() -> None:
    index = InMemorySemanticMemoryIndex()
    repository = InMemoryOutboxRepository(
        event=_event(SemanticMemoryOutboxOperation.UPSERT),
        record=_record(),
    )
    processor = SemanticMemoryOutboxProcessor(
        repository,
        index=index,
        embedding_provider=MappingEmbeddingProvider(),
        worker_id="semantic-test-worker",
    )

    assert asyncio.run(processor.process_once(limit=8)) == 1
    matches = asyncio.run(index.search(profile_id="profile-a", vector=(0.8, 0.6), limit=1))

    assert [(match.record_id, match.score) for match in matches] == [("memory-preference", 1.0)]
    assert repository.completed_ids == ["event-preference"]
    assert repository.rescheduled == []


def test_outbox_processor_removes_stale_index_for_non_active_memory() -> None:
    index = InMemorySemanticMemoryIndex()
    asyncio.run(index.upsert(record_id="memory-preference", profile_id="profile-a", vector=(0.8, 0.6)))
    repository = InMemoryOutboxRepository(
        event=_event(SemanticMemoryOutboxOperation.UPSERT),
        record=_record(MemoryState.REVOKED),
    )
    processor = SemanticMemoryOutboxProcessor(
        repository,
        index=index,
        embedding_provider=MappingEmbeddingProvider(),
        worker_id="semantic-test-worker",
    )

    assert asyncio.run(processor.process_once(limit=8)) == 1
    matches = asyncio.run(index.search(profile_id="profile-a", vector=(0.8, 0.6), limit=1))

    assert matches == ()
    assert repository.completed_ids == ["event-preference"]


def test_semantic_outbox_migration_writes_events_from_memory_state_changes() -> None:
    migration = Path("migrations/v2/006_semantic_memory_outbox.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS semantic_memory_outbox" in migration
    assert "CREATE TRIGGER trg_memory_records_semantic_insert" in migration
    assert "CREATE TRIGGER trg_memory_records_semantic_update" in migration
    assert "v2.006_semantic_memory_outbox" in migration
