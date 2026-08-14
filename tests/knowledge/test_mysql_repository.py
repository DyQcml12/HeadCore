from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.core.config import load_settings
from app.knowledge.models import AuditEvent, MemoryCandidate, MemoryScope, MemoryState
from app.knowledge.mysql_repository import MySQLKnowledgeRepository
from app.knowledge.semantic_outbox import SemanticMemoryOutboxState


NOW = datetime(2026, 7, 15, 1, 0, tzinfo=UTC)


class RecordingKnowledgeRepository(MySQLKnowledgeRepository):
    def __init__(self) -> None:
        super().__init__(
            replace(
                load_settings(),
                mysql_database="test_knowledge",
                mysql_user="test",
                mysql_password="test",
                database_v2_enabled=True,
            )
        )
        self.writes: list[tuple[str, tuple[object, ...]]] = []
        self.one: dict[str, object] | None = None
        self.rows: list[dict[str, object]] = []
        self.affected = 1

    async def _execute(self, sql, params):  # type: ignore[no-untyped-def]
        self.writes.append((sql, params))
        return self.affected

    async def _fetchone(self, sql, params):  # type: ignore[no-untyped-def]
        return self.one

    async def _fetchall(self, sql, params):  # type: ignore[no-untyped-def]
        return self.rows


def candidate() -> MemoryCandidate:
    return MemoryCandidate(
        id="candidate-1", profile_id="profile-1", key="reply.style", value="short",
        scope=MemoryScope.SAFE_PREFERENCE, source_type="message", source_id="message-1",
        confidence=0.9, created_at=NOW,
    )


async def test_candidate_round_trip_uses_lifecycle_table() -> None:
    repository = RecordingKnowledgeRepository()
    item = candidate()
    await repository.add_candidate(item)
    sql, params = repository.writes[0]

    assert "INSERT INTO memory_candidates" in sql
    assert params[0] == item.id
    repository.one = {
        "id": item.id, "profile_id": item.profile_id, "memory_key": item.key,
        "memory_value": item.value, "scope": item.scope.value,
        "source_type": item.source_type, "source_id": item.source_id,
        "confidence": item.confidence, "created_at": NOW, "persona_id": None,
        "expires_at": None, "observation_quality": None,
        "changes_authority": False, "idempotency_key": None, "state": item.state.value,
    }
    assert await repository.get_candidate(item.id) == item


async def test_audit_write_redacts_sensitive_details() -> None:
    repository = RecordingKnowledgeRepository()
    await repository.append_audit(
        AuditEvent(
            id="audit-1", entity_type="candidate", entity_id="candidate-1",
            action="submitted", actor_profile_id="profile-1",
            reason="token sk-123456789012345678901234", occurred_at=NOW,
            details={"authorization": "Bearer secret-token"},
        )
    )

    sql, params = repository.writes[0]
    assert "INSERT INTO memory_audit_events" in sql
    serialized = str(params)
    assert "sk-123456789012345678901234" not in serialized
    assert "Bearer secret-token" not in serialized


async def test_missing_update_fails_explicitly() -> None:
    repository = RecordingKnowledgeRepository()
    repository.affected = 0

    try:
        await repository.update_candidate_state("missing", MemoryState.DELETED)
    except KeyError as exc:
        assert exc.args == ("missing",)
    else:
        raise AssertionError("missing candidate update did not fail")


async def test_persistence_status_requires_tables_and_migration() -> None:
    repository = RecordingKnowledgeRepository()
    repository.rows = [
        {"TABLE_NAME": "memory_candidates"},
        {"TABLE_NAME": "memory_records"},
        {"TABLE_NAME": "memory_audit_events"},
    ]
    repository.one = None

    missing = await repository.get_persistence_status()
    assert missing.reason == "lifecycle_migration_missing"

    repository.one = {"version": "v2.002_knowledge_lifecycle"}
    ready = await repository.get_persistence_status()
    assert ready.durable is True
    assert ready.reason == "ready"


async def test_semantic_outbox_completion_and_retry_updates_are_bounded() -> None:
    repository = RecordingKnowledgeRepository()

    await repository.mark_completed("event-1")
    await repository.reschedule("event-2", reason="RuntimeError: database password=not-for-log")

    completed_sql, completed_params = repository.writes[0]
    retry_sql, retry_params = repository.writes[1]
    assert "UPDATE semantic_memory_outbox" in completed_sql
    assert completed_params == (
        SemanticMemoryOutboxState.COMPLETED.value,
        "event-1",
        SemanticMemoryOutboxState.PROCESSING.value,
    )
    assert "UPDATE semantic_memory_outbox" in retry_sql
    assert SemanticMemoryOutboxState.RETRY.value in retry_params
    assert "password" not in str(retry_params)


def test_migration_declares_required_tables_and_schema_version() -> None:
    from pathlib import Path

    sql = Path("migrations/v2/002_knowledge_lifecycle.sql").read_text(encoding="utf-8")
    for table in ("memory_candidates", "memory_records", "memory_audit_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "v2.002_knowledge_lifecycle" in sql
    assert "FOREIGN KEY (profile_id) REFERENCES profiles(id)" in sql
    assert "UNIQUE KEY uq_memory_candidates_idempotency" in sql
