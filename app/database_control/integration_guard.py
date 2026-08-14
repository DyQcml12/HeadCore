from __future__ import annotations


def validate_isolated_test_database(database_name: str) -> str:
    normalized = database_name.strip().lower()
    if not normalized:
        raise ValueError("database control integration database is required")
    if not (normalized.startswith("test_") or normalized.endswith("_test")):
        raise ValueError(
            "database control integration requires a database named test_* or *_test"
        )
    return database_name.strip()
