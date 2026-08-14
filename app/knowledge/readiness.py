from __future__ import annotations

from dataclasses import dataclass


KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES = frozenset(
    {
        "memory_candidates",
        "memory_records",
        "memory_audit_events",
    }
)


@dataclass(frozen=True)
class KnowledgePersistenceStatus:
    durable: bool
    write_ready: bool
    required_tables: dict[str, bool]
    reason: str
    migration_applied: bool = False
    enabled: bool = True


def assess_knowledge_persistence(
    available_tables: set[str] | frozenset[str],
    *,
    migration_applied: bool = True,
    enabled: bool = True,
) -> KnowledgePersistenceStatus:
    required = {
        table: table in available_tables
        for table in sorted(KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES)
    }
    ready = enabled and migration_applied and all(required.values())
    if not enabled:
        reason = "database_v2_disabled"
    elif not migration_applied:
        reason = "lifecycle_migration_missing"
    elif not all(required.values()):
        reason = "lifecycle_tables_missing"
    else:
        reason = "ready"
    return KnowledgePersistenceStatus(
        durable=ready,
        write_ready=ready,
        required_tables=required,
        reason=reason,
        migration_applied=migration_applied,
        enabled=enabled,
    )
