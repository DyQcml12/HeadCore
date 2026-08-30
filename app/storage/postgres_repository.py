from __future__ import annotations

import asyncio
import sys
from typing import Any

from app.core.config import Settings
from app.storage.mysql_repository import MySQLChatRepository


def postgres_is_configured(settings: Settings) -> bool:
    return bool(settings.postgres_database and settings.postgres_user and settings.postgres_password)


class PostgreSQLChatRepository(MySQLChatRepository):
    """PostgreSQL transport for the existing chat repository contract."""

    def _validate_settings(self) -> None:
        missing = [
            name
            for name, value in [
                ("POSTGRES_DATABASE", self.settings.postgres_database),
                ("POSTGRES_USER", self.settings.postgres_user),
                ("POSTGRES_PASSWORD", self.settings.postgres_password),
            ]
            if not value
        ]
        if missing:
            raise ValueError(
                "STORAGE_BACKEND=postgresql requires non-empty settings: " + ", ".join(missing)
            )

    async def _connect(self) -> Any:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for STORAGE_BACKEND=postgresql. "
                "Install dependencies with `python -m pip install -r requirements.txt`."
            ) from exc

        connect_kwargs = {
            "host": self.settings.postgres_host,
            "port": self.settings.postgres_port,
            "dbname": self.settings.postgres_database,
            "user": self.settings.postgres_user,
            "password": self.settings.postgres_password,
            "row_factory": dict_row,
        }
        # psycopg's async driver relies on add_reader/add_writer, which the
        # Windows ProactorEventLoop intentionally does not provide. Uvicorn's
        # CLI can select that loop even though app.main sets a selector policy,
        # so keep the repository usable by moving synchronous psycopg work to
        # a worker thread in that environment.
        loop = asyncio.get_running_loop()
        is_windows_proactor = sys.platform == "win32" and loop.__class__.__name__ == "ProactorEventLoop"
        if is_windows_proactor:
            connection = await asyncio.to_thread(psycopg.connect, **connect_kwargs)
            return _ThreadedPostgresConnection(connection)
        return await psycopg.AsyncConnection.connect(**connect_kwargs)

    async def _execute(self, sql: str, params: tuple[Any, ...]) -> int:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(sql, params)
            affected_rows = int(cursor.rowcount or 0)
            await connection.commit()
            return affected_rows
        except Exception:
            await connection.rollback()
            raise
        finally:
            await cursor.close()
            await connection.close()

    async def _fetchone(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row is not None else None
        finally:
            await cursor.close()
            await connection.close()

    async def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(sql, params)
            return [dict(row) for row in await cursor.fetchall()]
        finally:
            await cursor.close()
            await connection.close()


class _ThreadedPostgresConnection:
    """Async-shaped adapter for psycopg's blocking connection on Proactor."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def cursor(self) -> "_ThreadedPostgresCursor":
        return _ThreadedPostgresCursor(self._connection.cursor())

    async def commit(self) -> None:
        await asyncio.to_thread(self._connection.commit)

    async def rollback(self) -> None:
        await asyncio.to_thread(self._connection.rollback)

    async def close(self) -> None:
        await asyncio.to_thread(self._connection.close)


class _ThreadedPostgresCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount or 0)

    async def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        await asyncio.to_thread(self._cursor.execute, sql, params)

    async def fetchone(self) -> Any:
        return await asyncio.to_thread(self._cursor.fetchone)

    async def fetchall(self) -> list[Any]:
        return await asyncio.to_thread(self._cursor.fetchall)

    async def close(self) -> None:
        await asyncio.to_thread(self._cursor.close)
