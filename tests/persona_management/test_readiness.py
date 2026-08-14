from app.persona_management.readiness import (
    PERSONA_MANAGEMENT_REQUIRED_TABLES,
    assess_persona_management_persistence,
)


def test_persona_management_requires_enabled_database_migration_and_all_tables() -> None:
    tables = set(PERSONA_MANAGEMENT_REQUIRED_TABLES)
    assert "persona_management_operations" in tables
    ready = assess_persona_management_persistence(
        tables, migration_applied=True, database_v2_enabled=True
    )
    assert ready.durable is True
    assert ready.reason == "ready"

    assert assess_persona_management_persistence(
        tables, migration_applied=False, database_v2_enabled=True
    ).reason == "persona_management_migration_missing"
    assert assess_persona_management_persistence(
        set(), migration_applied=True, database_v2_enabled=True
    ).reason == "persona_management_tables_missing"
    assert assess_persona_management_persistence(
        tables, migration_applied=True, database_v2_enabled=False
    ).reason == "database_v2_disabled"
