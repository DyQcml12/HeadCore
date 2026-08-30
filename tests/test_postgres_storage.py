from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI

from app.core.config import load_settings
from app.storage.repository_factory import create_chat_repository
from app.storage.postgres_repository import _ThreadedPostgresConnection


def configured_postgres_settings(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgresql")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DATABASE", "hutao_chat_core")
    monkeypatch.setenv("POSTGRES_USER", "hutao_app")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-postgres-password")
    return load_settings()


def test_postgresql_backend_selects_a_postgresql_chat_repository(monkeypatch) -> None:
    settings = configured_postgres_settings(monkeypatch)

    repository = create_chat_repository(settings)

    assert type(repository).__name__ == "PostgreSQLChatRepository"
    assert settings.postgres_host == "127.0.0.1"
    assert settings.postgres_port == 5432


def test_postgresql_backend_requires_complete_connection_settings(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "postgresql")
    monkeypatch.setenv("POSTGRES_DATABASE", "")
    monkeypatch.setenv("POSTGRES_USER", "")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")

    try:
        create_chat_repository(load_settings())
    except ValueError as exc:
        assert "POSTGRES_DATABASE" in str(exc)
        assert "POSTGRES_USER" in str(exc)
        assert "POSTGRES_PASSWORD" in str(exc)
    else:
        raise AssertionError("postgresql backend should require connection settings")


def test_public_auth_runtime_uses_postgresql_when_that_storage_backend_is_selected(monkeypatch) -> None:
    from app.auth.runtime import configure_public_web_auth

    settings = replace(
        configured_postgres_settings(monkeypatch),
        public_web_auth_enabled=True,
        mysql_database="",
        mysql_user="",
        mysql_password="",
    )
    app = FastAPI()

    runtime = configure_public_web_auth(app, settings)

    assert runtime.authentication_enabled is True
    assert runtime.service is not None
    assert "/api/v1/auth/login" in {route.path for route in app.routes}


def test_postgresql_web_core_migration_covers_account_and_chat_contracts() -> None:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "postgres" / "001_web_core.sql"

    assert migration.is_file()
    contents = migration.read_text(encoding="utf-8")
    for table_name in (
        "profiles",
        "web_users",
        "web_sessions",
        "sessions",
        "messages",
        "model_invocations",
        "memories",
        "auth_audit_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in contents


def test_postgresql_runtime_instructions_expose_a_repeatable_migration_entrypoint() -> None:
    project_root = Path(__file__).resolve().parents[1]
    runner = project_root / "scripts" / "apply_postgres_web_migrations.py"
    env_example = (project_root / ".env.example").read_text(encoding="utf-8")

    assert runner.is_file()
    assert "STORAGE_BACKEND=postgresql" in env_example
    assert "POSTGRES_DATABASE=" in env_example
    assert "POSTGRES_PASSWORD=" in env_example


def test_postgresql_migration_runner_dry_run_executes_from_the_project_root() -> None:
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "apply_postgres_web_migrations.py"),
            "--dry-run",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "postgres.001_web_core" in completed.stdout


def test_threaded_postgres_adapter_preserves_async_repository_contract() -> None:
    class FakeCursor:
        rowcount = 1

        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            self.calls.append((sql, params))

        def fetchone(self) -> dict[str, str]:
            return {"id": "one"}

        def fetchall(self) -> list[dict[str, str]]:
            return [{"id": "one"}, {"id": "two"}]

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_value = FakeCursor()
            self.committed = False
            self.closed = False

        def cursor(self) -> FakeCursor:
            return self.cursor_value

        def commit(self) -> None:
            self.committed = True

        def close(self) -> None:
            self.closed = True

    async def exercise() -> None:
        connection = FakeConnection()
        adapter = _ThreadedPostgresConnection(connection)
        cursor = adapter.cursor()
        await cursor.execute("SELECT 1", ())
        assert cursor.rowcount == 1
        assert await cursor.fetchone() == {"id": "one"}
        assert await cursor.fetchall() == [{"id": "one"}, {"id": "two"}]
        await adapter.commit()
        await cursor.close()
        await adapter.close()
        assert connection.committed is True
        assert connection.closed is True

    asyncio.run(exercise())
