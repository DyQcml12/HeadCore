from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Protocol

from app.knowledge.models import AuditEvent, MemoryCandidate, MemoryRecord, MemoryState


class KnowledgeRepository(Protocol):
    async def add_candidate(self, candidate: MemoryCandidate) -> None: ...

    async def get_candidate(self, candidate_id: str) -> MemoryCandidate | None: ...

    async def get_candidate_by_idempotency_key(
        self, *, profile_id: str, idempotency_key: str
    ) -> MemoryCandidate | None: ...

    async def update_candidate_state(self, candidate_id: str, state: MemoryState) -> MemoryCandidate: ...

    async def list_candidates(
        self, *, profile_id: str | None = None, state: MemoryState | None = None, limit: int = 50
    ) -> tuple[MemoryCandidate, ...]: ...

    async def add_record(self, record: MemoryRecord) -> None: ...

    async def get_record(self, record_id: str) -> MemoryRecord | None: ...

    async def update_record(self, record: MemoryRecord) -> None: ...

    async def list_records(self, *, profile_id: str) -> tuple[MemoryRecord, ...]: ...

    async def append_audit(self, event: AuditEvent) -> None: ...

    async def list_audit_events(self, *, entity_id: str | None = None) -> tuple[AuditEvent, ...]: ...

    async def apply_approval(
        self,
        *,
        candidate_id: str,
        superseded_records: tuple[MemoryRecord, ...],
        record: MemoryRecord,
        audit_events: tuple[AuditEvent, ...],
    ) -> None: ...


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self._candidates: dict[str, MemoryCandidate] = {}
        self._records: dict[str, MemoryRecord] = {}
        self._audit_events: list[AuditEvent] = []
        self._lock = asyncio.Lock()

    async def add_candidate(self, candidate: MemoryCandidate) -> None:
        async with self._lock:
            if candidate.id in self._candidates:
                raise ValueError(f"candidate already exists: {candidate.id}")
            self._candidates[candidate.id] = candidate

    async def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        async with self._lock:
            return self._candidates.get(candidate_id)

    async def get_candidate_by_idempotency_key(
        self, *, profile_id: str, idempotency_key: str
    ) -> MemoryCandidate | None:
        async with self._lock:
            return next(
                (
                    item for item in self._candidates.values()
                    if item.profile_id == profile_id
                    and item.idempotency_key == idempotency_key
                ),
                None,
            )

    async def update_candidate_state(self, candidate_id: str, state: MemoryState) -> MemoryCandidate:
        async with self._lock:
            candidate = self._candidates[candidate_id]
            updated = replace(candidate, state=state)
            self._candidates[candidate_id] = updated
            return updated

    async def list_candidates(
        self, *, profile_id: str | None = None, state: MemoryState | None = None, limit: int = 50
    ) -> tuple[MemoryCandidate, ...]:
        async with self._lock:
            items = [
                item for item in self._candidates.values()
                if (profile_id is None or item.profile_id == profile_id)
                and (state is None or item.state == state)
            ]
            items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
            return tuple(items[:max(1, min(limit, 100))])

    async def add_record(self, record: MemoryRecord) -> None:
        async with self._lock:
            if record.id in self._records:
                raise ValueError(f"record already exists: {record.id}")
            self._records[record.id] = record

    async def get_record(self, record_id: str) -> MemoryRecord | None:
        async with self._lock:
            return self._records.get(record_id)

    async def update_record(self, record: MemoryRecord) -> None:
        async with self._lock:
            if record.id not in self._records:
                raise KeyError(record.id)
            self._records[record.id] = record

    async def list_records(self, *, profile_id: str) -> tuple[MemoryRecord, ...]:
        async with self._lock:
            return tuple(record for record in self._records.values() if record.profile_id == profile_id)

    async def append_audit(self, event: AuditEvent) -> None:
        async with self._lock:
            self._audit_events.append(event)

    async def list_audit_events(self, *, entity_id: str | None = None) -> tuple[AuditEvent, ...]:
        async with self._lock:
            if entity_id is None:
                return tuple(self._audit_events)
            return tuple(event for event in self._audit_events if event.entity_id == entity_id)

    async def apply_approval(
        self,
        *,
        candidate_id: str,
        superseded_records: tuple[MemoryRecord, ...],
        record: MemoryRecord,
        audit_events: tuple[AuditEvent, ...],
    ) -> None:
        async with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                raise KeyError(candidate_id)
            if candidate.state != MemoryState.CANDIDATE:
                raise ValueError(f"candidate is already {candidate.state.value}")
            if record.id in self._records:
                raise ValueError(f"record already exists: {record.id}")
            for updated in superseded_records:
                current = self._records.get(updated.id)
                if current is None or current.state != MemoryState.ACTIVE:
                    raise ValueError(f"conflicting record is no longer active: {updated.id}")
            for updated in superseded_records:
                self._records[updated.id] = updated
            self._records[record.id] = record
            self._candidates[candidate_id] = replace(candidate, state=MemoryState.ACTIVE)
            self._audit_events.extend(audit_events)
