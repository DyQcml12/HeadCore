from __future__ import annotations

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

        return await psycopg.AsyncConnection.connect(
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            dbname=self.settings.postgres_database,
            user=self.settings.postgres_user,
            password=self.settings.postgres_password,
            row_factory=dict_row,
        )

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
