from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol
from uuid import uuid4


PersonaAuditStatus = Literal["accepted", "rejected", "failed"]


@dataclass(frozen=True)
class PersonaControlAuditEvent:
    audit_id: str
    actor_profile_id: str
    operation: str
    target_type: str
    target_id: str
    status: PersonaAuditStatus
    reason_code: str
    created_at: datetime


class PersonaControlAuditSink(Protocol):
    async def record(
        self,
        *,
        actor_profile_id: str,
        operation: str,
        target_type: str,
        target_id: str,
        status: PersonaAuditStatus,
        reason_code: str,
    ) -> PersonaControlAuditEvent: ...


class DatabaseControlAuditWriter(Protocol):
    async def record_control_operation(
        self,
        *,
        actor: object | None,
        actor_profile_id: str | None,
        platform: str,
        operation: str,
        status: str,
        reason_code: str,
    ) -> None: ...


class DatabasePersonaControlAuditSink:
    """Writes redacted S5 control events through the existing S1 audit path."""

    def __init__(self, writer: DatabaseControlAuditWriter) -> None:
        self._writer = writer

    async def record(
        self,
        *,
        actor_profile_id: str,
        operation: str,
        target_type: str,
        target_id: str,
        status: PersonaAuditStatus,
        reason_code: str,
    ) -> PersonaControlAuditEvent:
        del target_type, target_id
        await self._writer.record_control_operation(
            actor=None,
            actor_profile_id=actor_profile_id,
            platform="control",
            operation=f"persona_{operation}",
            status=status,
            reason_code=reason_code,
        )
        return PersonaControlAuditEvent(
            audit_id=uuid4().hex,
            actor_profile_id=actor_profile_id,
            operation=operation,
            target_type="redacted",
            target_id="redacted",
            status=status,
            reason_code=reason_code,
            created_at=datetime.now(timezone.utc),
        )


class InMemoryPersonaControlAuditSink:
    def __init__(self) -> None:
        self._events: list[PersonaControlAuditEvent] = []
        self._lock = asyncio.Lock()

    async def record(
        self,
        *,
        actor_profile_id: str,
        operation: str,
        target_type: str,
        target_id: str,
        status: PersonaAuditStatus,
        reason_code: str,
    ) -> PersonaControlAuditEvent:
        event = PersonaControlAuditEvent(
            audit_id=uuid4().hex,
            actor_profile_id=actor_profile_id,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            status=status,
            reason_code=reason_code,
            created_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._events.append(event)
        return event

    async def list_events(self) -> tuple[PersonaControlAuditEvent, ...]:
        async with self._lock:
            return tuple(self._events)
