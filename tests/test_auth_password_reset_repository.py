from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.auth.mysql_repository import MySQLAuthRepository
from app.core.config import load_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingCursor:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.statements.append((sql, params))

    async def fetchone(self) -> dict[str, object] | None:
        return self.row

    def close(self) -> None:
        return None


class RecordingConnection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.cursor_instance = RecordingCursor(row)
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None


class RecordingPasswordResetRepository(MySQLAuthRepository):
    def __init__(self, row: dict[str, object] | None = None) -> None:
        settings = load_settings()
        object.__setattr__(settings, "mysql_database", "hutao_chat_core")
        object.__setattr__(settings, "mysql_user", "test-user")
        object.__setattr__(settings, "mysql_password", "test-password")
        super().__init__(settings)
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.connection = RecordingConnection(row)

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:  # type: ignore[override]
        self.statements.append((sql, params))
        return 1

    async def _connect(self):  # type: ignore[override]
        return self.connection


def test_password_reset_migration_stores_hashes_only_and_revokes_sessions() -> None:
    migration_path = PROJECT_ROOT / "migrations" / "v2" / "005_public_web_password_reset.sql"
    migration = migration_path.read_text(encoding="utf-8") if migration_path.exists() else ""

    assert "CREATE TABLE IF NOT EXISTS password_reset_tokens" in migration
    assert "token_hash CHAR(64) NOT NULL" in migration
    assert "token VARCHAR" not in migration
    assert "password_reset_requested" in migration
    assert "password_reset_completed" in migration


def test_mysql_password_reset_supersedes_prior_tokens_without_storing_raw_values() -> None:
    assert hasattr(MySQLAuthRepository, "create_password_reset_token")
    repository = RecordingPasswordResetRepository()
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)

    asyncio.run(
        repository.create_password_reset_token(
            user_id="user-1",
            token_hash="a" * 64,
            expires_at=now + timedelta(minutes=30),
            created_at=now,
        )
    )

    statements = "\n".join(sql for sql, _params in repository.statements)
    params = tuple(value for _sql, values in repository.statements for value in values)
    assert "UPDATE password_reset_tokens" in statements
    assert "INSERT INTO password_reset_tokens" in statements
    assert "a" * 64 in params
    assert all("opaque-reset-token" not in str(value) for value in params)


def test_mysql_password_reset_consumption_updates_password_and_revokes_all_sessions() -> None:
    assert hasattr(MySQLAuthRepository, "consume_password_reset_token")
    now = datetime(2026, 7, 30, tzinfo=timezone.utc)
    repository = RecordingPasswordResetRepository(
        {
            "id": "reset-1",
            "user_id": "user-1",
            "expires_at": now + timedelta(minutes=10),
            "used_at": None,
            "profile_id": "profile-1",
            "email_normalized": "reader@example.com",
            "password_hash": "old-password-hash",
            "status": "active",
        }
    )

    user = asyncio.run(
        repository.consume_password_reset_token(
            token_hash="b" * 64,
            password_hash="new-password-hash",
            now=now,
        )
    )

    statements = "\n".join(sql for sql, _params in repository.connection.cursor_instance.statements)
    params = tuple(
        value
        for _sql, values in repository.connection.cursor_instance.statements
        for value in values
    )
    assert user is not None
    assert user.id == "user-1"
    assert repository.connection.committed is True
    assert "UPDATE web_users" in statements
    assert "UPDATE web_sessions" in statements
    assert "new-password-hash" in params
