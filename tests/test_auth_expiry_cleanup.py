from __future__ import annotations

from datetime import datetime, timezone

from scripts.auth_expiry_cleanup import build_expiry_cleanup_queries, run_cleanup


def test_cleanup_queries_cover_all_expiring_tables() -> None:
    queries = build_expiry_cleanup_queries(datetime(2026, 8, 14, tzinfo=timezone.utc))

    labels = [label for label, _count, _delete in queries]
    assert labels == [
        "web_sessions",
        "email_verification_tokens",
        "password_reset_tokens",
        "registration_attempts",
    ]
    for _label, count_sql, delete_sql in queries:
        assert count_sql.startswith("SELECT COUNT(*)")
        assert delete_sql.startswith("DELETE FROM")
        assert "%s" in delete_sql


class RecordingRepository:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.counts = [42, 0, 7, 3]

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:
        self.statements.append((sql, params))
        return 1

    async def _fetchone(self, sql: str, params: tuple[object, ...]) -> dict[str, object] | None:
        return {"count": self.counts.pop(0) if self.counts else 0}


def test_dry_run_only_counts_and_reports() -> None:
    import asyncio

    repository = RecordingRepository()

    result = asyncio.run(
        run_cleanup(repository, now=datetime(2026, 8, 14, tzinfo=timezone.utc), dry_run=True)
    )

    assert result["status"] == "OK"
    assert result["dry_run"] is True
    assert repository.statements == []
    assert [item["would_delete"] for item in result["items"]] == [42, 0, 7, 3]


class FailingRepository:
    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:
        raise RuntimeError("table missing")

    async def _fetchone(self, sql: str, params: tuple[object, ...]) -> dict[str, object] | None:
        raise RuntimeError("table missing")


def test_cleanup_reports_per_table_errors_without_crashing() -> None:
    import asyncio

    repository = FailingRepository()

    result = asyncio.run(
        run_cleanup(repository, now=datetime(2026, 8, 14, tzinfo=timezone.utc), dry_run=True)
    )

    assert result["status"] == "OK"
    assert all("error" in item for item in result["items"])


def test_apply_executes_deletes() -> None:
    import asyncio

    repository = RecordingRepository()

    result = asyncio.run(
        run_cleanup(repository, now=datetime(2026, 8, 14, tzinfo=timezone.utc), dry_run=False)
    )

    assert len(repository.statements) == 4
    assert all(sql.startswith("DELETE FROM") for sql, _params in repository.statements)
    assert result["items"][0]["deleted"] == 1
