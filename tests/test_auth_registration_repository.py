from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from asyncmy.errors import IntegrityError as MysqlIntegrityError

from app.auth.mysql_repository import MySQLAuthRepository
from app.auth.postgres_repository import PostgreSQLAuthRepository
from app.auth.registration import RegistrationError
from app.core.config import load_settings


def mysql_settings():
    return replace(
        load_settings(),
        database_v2_enabled=True,
        mysql_database="test_hutao",
        mysql_user="test_user",
        mysql_password="test_password",
    )


def postgres_settings():
    return replace(
        load_settings(),
        storage_backend="postgresql",
        postgres_database="test_db",
        postgres_user="test_user",
        postgres_password="test_password",
    )


def pending_values() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "email_normalized": "dup@example.test",
        "display_name": "Dup",
        "password_hash": "hash",
        "verification_token_hash": "tokenhash",
        "verification_expires_at": now + timedelta(minutes=30),
        "created_at": now,
    }


async def _fake_connection(connection: object) -> object:
    return connection


class FakeMysqlCursor:
    def __init__(self, failure: Exception | None) -> None:
        self._failure = failure

    async def execute(self, sql: str, params: tuple[object, ...]) -> None:
        if self._failure is not None and "INSERT INTO web_users" in sql:
            raise self._failure

    def close(self) -> None:
        pass


class FakeMysqlConnection:
    def __init__(self, cursor: FakeMysqlCursor) -> None:
        self._cursor = cursor
        self.rolled_back = False
        self.committed = False

    def cursor(self) -> FakeMysqlCursor:
        return self._cursor

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        pass


def test_mysql_duplicate_email_becomes_registration_error() -> None:
    connection = FakeMysqlConnection(
        FakeMysqlCursor(MysqlIntegrityError(1062, "Duplicate entry 'dup@example.test' for key 'web_users.uq_web_users_email'")),
    )
    repository = MySQLAuthRepository(mysql_settings())
    repository._connect = (  # type: ignore[method-assign]
        lambda: _fake_connection(connection)
    )

    with pytest.raises(RegistrationError, match="email already registered"):
        asyncio.run(repository.create_pending_user(**pending_values()))
    assert connection.rolled_back is True
    assert connection.committed is False


def test_mysql_unrelated_error_is_reraised() -> None:
    connection = FakeMysqlConnection(FakeMysqlCursor(RuntimeError("boom")))
    repository = MySQLAuthRepository(mysql_settings())
    repository._connect = (  # type: ignore[method-assign]
        lambda: _fake_connection(connection)
    )

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(repository.create_pending_user(**pending_values()))
    assert connection.rolled_back is True


class FakePgCursor:
    def __init__(self, failure: Exception | None) -> None:
        self._failure = failure

    async def execute(self, sql: str, params: tuple[object, ...]) -> None:
        if self._failure is not None and "INSERT INTO web_users" in sql:
            raise self._failure

    async def close(self) -> None:
        pass


class FakePgConnection:
    def __init__(self, cursor: FakePgCursor) -> None:
        self._cursor = cursor
        self.rolled_back = False

    def cursor(self) -> FakePgCursor:
        return self._cursor

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        pass


def test_postgres_duplicate_email_becomes_registration_error() -> None:
    import psycopg.errors

    connection = FakePgConnection(
        FakePgCursor(
            psycopg.errors.UniqueViolation(
                'duplicate key value violates unique constraint "web_users_email_normalized_key"',
            ),
        ),
    )
    repository = PostgreSQLAuthRepository(postgres_settings())
    repository._connect = (  # type: ignore[method-assign]
        lambda: _fake_connection(connection)
    )

    with pytest.raises(RegistrationError, match="email already registered"):
        asyncio.run(repository.create_pending_user(**pending_values()))
    assert connection.rolled_back is True
