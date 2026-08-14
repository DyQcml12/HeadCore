from app.knowledge import (
    KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES,
    assess_knowledge_persistence,
)


def test_lifecycle_persistence_fails_closed_when_tables_are_missing() -> None:
    status = assess_knowledge_persistence({"memories", "profile_portraits"})

    assert status.durable is False
    assert status.write_ready is False
    assert status.reason == "lifecycle_tables_missing"
    assert all(available is False for available in status.required_tables.values())


def test_lifecycle_persistence_is_ready_only_with_every_required_table() -> None:
    status = assess_knowledge_persistence(set(KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES))

    assert status.durable is True
    assert status.write_ready is True
    assert status.reason == "ready"
    assert all(status.required_tables.values())


def test_partial_lifecycle_schema_is_not_write_ready() -> None:
    available = set(KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES)
    available.remove("memory_audit_events")

    status = assess_knowledge_persistence(available)

    assert status.write_ready is False
    assert status.required_tables["memory_audit_events"] is False


def test_tables_without_lifecycle_migration_are_not_ready() -> None:
    status = assess_knowledge_persistence(
        set(KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES),
        migration_applied=False,
    )

    assert status.durable is False
    assert status.write_ready is False
    assert status.reason == "lifecycle_migration_missing"


def test_disabled_database_fails_closed_even_with_schema() -> None:
    status = assess_knowledge_persistence(
        set(KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES),
        enabled=False,
    )

    assert status.durable is False
    assert status.reason == "database_v2_disabled"
