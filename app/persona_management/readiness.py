from __future__ import annotations

from dataclasses import dataclass


PERSONA_MANAGEMENT_SCHEMA_VERSION = "v2.003_persona_management"
PERSONA_MANAGEMENT_REQUIRED_TABLES = frozenset(
    {
        "persona_management_drafts",
        "persona_management_validations",
        "persona_management_versions",
        "persona_management_releases",
        "persona_management_bindings",
        "persona_management_operations",
    }
)


@dataclass(frozen=True)
class PersonaManagementPersistenceStatus:
    durable: bool
    write_ready: bool
    migration_applied: bool
    required_tables: dict[str, bool]
    reason: str


def assess_persona_management_persistence(
    available_tables: set[str] | frozenset[str],
    *,
    migration_applied: bool,
    database_v2_enabled: bool,
) -> PersonaManagementPersistenceStatus:
    required = {
        table: table in available_tables
        for table in sorted(PERSONA_MANAGEMENT_REQUIRED_TABLES)
    }
    ready = database_v2_enabled and migration_applied and all(required.values())
    if not database_v2_enabled:
        reason = "database_v2_disabled"
    elif not migration_applied:
        reason = "persona_management_migration_missing"
    elif not all(required.values()):
        reason = "persona_management_tables_missing"
    else:
        reason = "ready"
    return PersonaManagementPersistenceStatus(
        durable=ready,
        write_ready=ready,
        migration_applied=migration_applied,
        required_tables=required,
        reason=reason,
    )
