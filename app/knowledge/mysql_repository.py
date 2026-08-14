from __future__ import annotations

import json
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.config import Settings
from app.core.security import redact_secrets
from app.knowledge.models import (
    AuditEvent,
    MemoryCandidate,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from app.knowledge.readiness import (
    KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES,
    KnowledgePersistenceStatus,
    assess_knowledge_persistence,
)
from app.knowledge.semantic_outbox import (
    SemanticMemoryOutboxEvent,
    SemanticMemoryOutboxOperation,
    SemanticMemoryOutboxState,
)
from app.storage.mysql_repository import MySQLChatRepository


_SENSITIVE_DETAIL_KEYS = frozenset(
    {"authorization", "api_key", "apikey", "password", "secret", "token"}
)


class MySQLKnowledgeRepository(MySQLChatRepository):
    """Database V2 adapter for the public S4 repository contract."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    async def get_persistence_status(self) -> KnowledgePersistenceStatus:
        tables = tuple(sorted(KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES))
        placeholders = ", ".join("%s" for _table in tables)
        rows = await self._fetchall(
            f"""
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders})
            """,
            (self.settings.mysql_database, *tables),
        )
        available = {str(row["TABLE_NAME"]) for row in rows}
        migration = await self._fetchone(
            """
            SELECT version FROM schema_migrations
            WHERE version = %s LIMIT 1
            """,
            ("v2.002_knowledge_lifecycle",),
        )
        return assess_knowledge_persistence(
            available,
            migration_applied=migration is not None,
            enabled=self.settings.database_v2_enabled,
        )

    async def add_candidate(self, candidate: MemoryCandidate) -> None:
        await self._execute(
            """
            INSERT INTO memory_candidates (
                id, profile_id, memory_key, memory_value, scope, source_type,
                source_id, idempotency_key, confidence, persona_id, expires_at,
                observation_quality, changes_authority, state, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                candidate.id, candidate.profile_id, candidate.key, candidate.value,
                candidate.scope.value, candidate.source_type, candidate.source_id,
                candidate.idempotency_key, candidate.confidence, candidate.persona_id, candidate.expires_at,
                candidate.observation_quality, candidate.changes_authority,
                candidate.state.value, candidate.created_at, candidate.created_at,
            ),
        )

    async def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        row = await self._fetchone(
            "SELECT * FROM memory_candidates WHERE id = %s LIMIT 1",
            (candidate_id,),
        )
        return _candidate_from_row(row) if row else None

    async def get_candidate_by_idempotency_key(
        self, *, profile_id: str, idempotency_key: str
    ) -> MemoryCandidate | None:
        row = await self._fetchone(
            """
            SELECT * FROM memory_candidates
            WHERE profile_id = %s AND idempotency_key = %s
            LIMIT 1
            """,
            (profile_id, idempotency_key),
        )
        return _candidate_from_row(row) if row else None

    async def update_candidate_state(
        self, candidate_id: str, state: MemoryState
    ) -> MemoryCandidate:
        affected = await self._execute(
            """
            UPDATE memory_candidates
            SET state = %s, updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = %s
            """,
            (state.value, candidate_id),
        )
        if affected != 1:
            raise KeyError(candidate_id)
        candidate = await self.get_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        return candidate

    async def list_candidates(
        self, *, profile_id: str | None = None, state: MemoryState | None = None, limit: int = 50
    ) -> tuple[MemoryCandidate, ...]:
        conditions: list[str] = []
        params: list[object] = []
        if profile_id is not None:
            conditions.append("profile_id = %s")
            params.append(profile_id)
        if state is not None:
            conditions.append("state = %s")
            params.append(state.value)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        bounded = max(1, min(limit, 100))
        rows = await self._fetchall(
            f"SELECT * FROM memory_candidates{where} ORDER BY created_at DESC, id DESC LIMIT %s",
            (*params, bounded),
        )
        return tuple(_candidate_from_row(row) for row in rows)

    async def add_record(self, record: MemoryRecord) -> None:
        await self._execute(
            """
            INSERT INTO memory_records (
                id, candidate_id, profile_id, memory_key, memory_value, scope,
                source_type, source_id, confidence, state, persona_id, expires_at,
                supersedes_id, state_reason, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _record_params(record),
        )

    async def get_record(self, record_id: str) -> MemoryRecord | None:
        row = await self._fetchone(
            "SELECT * FROM memory_records WHERE id = %s LIMIT 1",
            (record_id,),
        )
        return _record_from_row(row) if row else None

    async def update_record(self, record: MemoryRecord) -> None:
        affected = await self._execute(
            """
            UPDATE memory_records
            SET state = %s, expires_at = %s, supersedes_id = %s,
                state_reason = %s, updated_at = %s, row_version = row_version + 1
            WHERE id = %s
            """,
            (
                record.state.value, record.expires_at, record.supersedes_id,
                record.state_reason, record.updated_at, record.id,
            ),
        )
        if affected != 1:
            raise KeyError(record.id)

    async def list_records(self, *, profile_id: str) -> tuple[MemoryRecord, ...]:
        rows = await self._fetchall(
            """
            SELECT * FROM memory_records
            WHERE profile_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (profile_id,),
        )
        return tuple(_record_from_row(row) for row in rows)

    async def append_audit(self, event: AuditEvent) -> None:
        await self._execute(
            """
            INSERT INTO memory_audit_events (
                id, entity_type, entity_id, action, actor_profile_id,
                reason, details_json, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _audit_params(event),
        )

    async def list_audit_events(
        self, *, entity_id: str | None = None
    ) -> tuple[AuditEvent, ...]:
        if entity_id is None:
            rows = await self._fetchall(
                "SELECT * FROM memory_audit_events ORDER BY occurred_at ASC, id ASC",
                (),
            )
        else:
            rows = await self._fetchall(
                """
                SELECT * FROM memory_audit_events
                WHERE entity_id = %s
                ORDER BY occurred_at ASC, id ASC
                """,
                (entity_id,),
            )
        return tuple(_audit_from_row(row) for row in rows)

    async def claim_pending(
        self,
        *,
        worker_id: str,
        limit: int,
    ) -> tuple[SemanticMemoryOutboxEvent, ...]:
        if not worker_id.strip() or limit <= 0:
            return ()
        bounded_limit = min(limit, 100)
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(
                """
                SELECT id, memory_record_id, profile_id, operation, state, attempts, created_at
                FROM semantic_memory_outbox
                WHERE (state IN ('pending', 'retry') AND available_at <= CURRENT_TIMESTAMP(3))
                   OR (state = 'processing' AND lease_expires_at <= CURRENT_TIMESTAMP(3))
                ORDER BY created_at ASC, id ASC
                LIMIT %s FOR UPDATE SKIP LOCKED
                """,
                (bounded_limit,),
            )
            rows = list(await cursor.fetchall())
            if not rows:
                await connection.commit()
                return ()
            for row in rows:
                await cursor.execute(
                    """
                    UPDATE semantic_memory_outbox
                    SET state = %s,
                        attempts = attempts + 1,
                        worker_id = %s,
                        lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(3), INTERVAL 5 MINUTE),
                        last_error = NULL
                    WHERE id = %s
                    """,
                    (SemanticMemoryOutboxState.PROCESSING.value, worker_id.strip()[:128], row["id"]),
                )
            await connection.commit()
            return tuple(
                SemanticMemoryOutboxEvent(
                    id=str(row["id"]),
                    memory_record_id=str(row["memory_record_id"]),
                    profile_id=str(row["profile_id"]),
                    operation=SemanticMemoryOutboxOperation(str(row["operation"])),
                    state=SemanticMemoryOutboxState.PROCESSING,
                    attempts=int(row["attempts"]) + 1,
                    created_at=_datetime(row["created_at"]),
                )
                for row in rows
            )
        except Exception:
            await connection.rollback()
            raise
        finally:
            close_result = cursor.close()
            if inspect.isawaitable(close_result):
                await close_result
            connection.close()

    async def mark_completed(self, event_id: str) -> None:
        affected = await self._execute(
            """
            UPDATE semantic_memory_outbox
            SET state = %s, completed_at = CURRENT_TIMESTAMP(3),
                lease_expires_at = NULL, worker_id = NULL, last_error = NULL
            WHERE id = %s AND state = %s
            """,
            (
                SemanticMemoryOutboxState.COMPLETED.value,
                event_id,
                SemanticMemoryOutboxState.PROCESSING.value,
            ),
        )
        if affected != 1:
            raise KeyError(event_id)

    async def reschedule(self, event_id: str, *, reason: str) -> None:
        safe_reason = _safe_outbox_reason(reason)
        affected = await self._execute(
            """
            UPDATE semantic_memory_outbox
            SET state = %s,
                available_at = DATE_ADD(
                    CURRENT_TIMESTAMP(3), INTERVAL LEAST(POW(2, attempts), 300) SECOND
                ),
                lease_expires_at = NULL, worker_id = NULL, last_error = %s
            WHERE id = %s AND state = %s
            """,
            (
                SemanticMemoryOutboxState.RETRY.value,
                safe_reason,
                event_id,
                SemanticMemoryOutboxState.PROCESSING.value,
            ),
        )
        if affected != 1:
            raise KeyError(event_id)

    async def apply_approval(
        self,
        *,
        candidate_id: str,
        superseded_records: tuple[MemoryRecord, ...],
        record: MemoryRecord,
        audit_events: tuple[AuditEvent, ...],
    ) -> None:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(
                "SELECT state FROM memory_candidates WHERE id = %s FOR UPDATE",
                (candidate_id,),
            )
            candidate_row = await cursor.fetchone()
            if candidate_row is None:
                raise KeyError(candidate_id)
            if str(candidate_row["state"]) != MemoryState.CANDIDATE.value:
                raise ValueError(f"candidate is already {candidate_row['state']}")

            for updated in superseded_records:
                await cursor.execute(
                    """
                    UPDATE memory_records
                    SET state = %s, state_reason = %s, updated_at = %s,
                        row_version = row_version + 1
                    WHERE id = %s AND state = %s
                    """,
                    (
                        updated.state.value, updated.state_reason, updated.updated_at,
                        updated.id, MemoryState.ACTIVE.value,
                    ),
                )
                if int(getattr(cursor, "rowcount", 0) or 0) != 1:
                    raise ValueError(f"conflicting record is no longer active: {updated.id}")

            await cursor.execute(
                """
                INSERT INTO memory_records (
                    id, candidate_id, profile_id, memory_key, memory_value, scope,
                    source_type, source_id, confidence, state, persona_id, expires_at,
                    supersedes_id, state_reason, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                _record_params(record),
            )
            await cursor.execute(
                """
                UPDATE memory_candidates
                SET state = %s, updated_at = %s
                WHERE id = %s AND state = %s
                """,
                (
                    MemoryState.ACTIVE.value, record.updated_at, candidate_id,
                    MemoryState.CANDIDATE.value,
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) != 1:
                raise ValueError("candidate state changed during approval")
            for event in audit_events:
                await cursor.execute(
                    """
                    INSERT INTO memory_audit_events (
                        id, entity_type, entity_id, action, actor_profile_id,
                        reason, details_json, occurred_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    _audit_params(event),
                )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            close_result = cursor.close()
            if inspect.isawaitable(close_result):
                await close_result
            connection.close()


def _record_params(record: MemoryRecord) -> tuple[Any, ...]:
    return (
        record.id, record.candidate_id, record.profile_id, record.key, record.value,
        record.scope.value, record.source_type, record.source_id, record.confidence,
        record.state.value, record.persona_id, record.expires_at,
        record.supersedes_id, record.state_reason, record.created_at, record.updated_at,
    )


def _audit_params(event: AuditEvent) -> tuple[Any, ...]:
    details = {}
    for key, value in event.details.items():
        normalized_key = str(key).strip().lower()
        details[str(key)] = (
            "<REDACTED>"
            if normalized_key in _SENSITIVE_DETAIL_KEYS
            else redact_secrets(str(value))
        )
    return (
        event.id, event.entity_type, event.entity_id, event.action,
        event.actor_profile_id or None, redact_secrets(event.reason),
        json.dumps(details, ensure_ascii=False), event.occurred_at,
    )


def _candidate_from_row(row: dict[str, Any]) -> MemoryCandidate:
    return MemoryCandidate(
        id=str(row["id"]), profile_id=str(row["profile_id"]),
        key=str(row["memory_key"]), value=str(row["memory_value"]),
        scope=MemoryScope(str(row["scope"])), source_type=str(row["source_type"]),
        source_id=str(row["source_id"]), confidence=_float(row["confidence"]),
        created_at=_datetime(row["created_at"]),
        persona_id=_optional_str(row.get("persona_id")),
        expires_at=_optional_datetime(row.get("expires_at")),
        observation_quality=(
            _float(row["observation_quality"])
            if row.get("observation_quality") is not None else None
        ),
        changes_authority=bool(row.get("changes_authority")),
        idempotency_key=_optional_str(row.get("idempotency_key")),
        state=MemoryState(str(row["state"])),
    )


def _record_from_row(row: dict[str, Any]) -> MemoryRecord:
    return MemoryRecord(
        id=str(row["id"]), candidate_id=str(row["candidate_id"]),
        profile_id=str(row["profile_id"]), key=str(row["memory_key"]),
        value=str(row["memory_value"]), scope=MemoryScope(str(row["scope"])),
        source_type=str(row["source_type"]), source_id=str(row["source_id"]),
        confidence=_float(row["confidence"]), state=MemoryState(str(row["state"])),
        created_at=_datetime(row["created_at"]), updated_at=_datetime(row["updated_at"]),
        persona_id=_optional_str(row.get("persona_id")),
        expires_at=_optional_datetime(row.get("expires_at")),
        supersedes_id=_optional_str(row.get("supersedes_id")),
        state_reason=str(row.get("state_reason") or ""),
    )


def _audit_from_row(row: dict[str, Any]) -> AuditEvent:
    raw_details = row.get("details_json")
    if isinstance(raw_details, str):
        details = json.loads(raw_details) if raw_details else {}
    else:
        details = raw_details or {}
    return AuditEvent(
        id=str(row["id"]), entity_type=str(row["entity_type"]),
        entity_id=str(row["entity_id"]), action=str(row["action"]),
        actor_profile_id=str(row.get("actor_profile_id") or ""),
        reason=str(row.get("reason") or ""), occurred_at=_datetime(row["occurred_at"]),
        details=details,
    )


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _optional_datetime(value: object | None) -> datetime | None:
    return _datetime(value) if value is not None else None


def _optional_str(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _float(value: object) -> float:
    return float(value if not isinstance(value, Decimal) else str(value))


def _safe_outbox_reason(reason: str) -> str:
    lowered = reason.lower()
    if any(marker in lowered for marker in _SENSITIVE_DETAIL_KEYS):
        return "semantic_sync_failed"
    normalized = "".join(
        character
        for character in lowered.strip()
        if character.isascii() and (character.isalnum() or character in {"_", "-", ":"})
    )
    return normalized[:64] or "semantic_sync_failed"
