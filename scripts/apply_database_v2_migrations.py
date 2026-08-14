from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.storage.mysql_repository import MySQLChatRepository


MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "v2"
TARGET_DATABASE_NAME = "hutao_chat_core"


@dataclass(frozen=True)
class DatabaseV2Migration:
    version: str
    description: str
    path: Path


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[DatabaseV2Migration]:
    migrations: list[DatabaseV2Migration] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        stem = path.stem
        migrations.append(
            DatabaseV2Migration(
                version="v2." + stem,
                description=stem.replace("_", " "),
                path=path,
            )
        )
    return migrations


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    delimiter = ";"
    for raw_line in sql.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        if line.upper().startswith("DELIMITER "):
            delimiter = line.split(None, 1)[1]
            continue
        current.append(raw_line)
        if line.endswith(delimiter):
            statement = "\n".join(current).rstrip()
            statements.append(statement[: -len(delimiter)].strip())
            current = []
    if current:
        statements.append("\n".join(current).strip())
    return statements


def validate_target_database(database_name: str, *, allow_non_target: bool = False) -> None:
    if allow_non_target:
        return
    if database_name != TARGET_DATABASE_NAME:
        raise ValueError(
            "Database V2 migrations target MYSQL_DATABASE=hutao_chat_core. "
            f"Current MYSQL_DATABASE={database_name!r}. "
            "Use --allow-non-hutao-chat-core only for isolated test databases."
        )


async def ensure_schema_migrations_table(repository: MySQLChatRepository) -> None:
    await repository._execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(128) NOT NULL,
            description VARCHAR(255) NOT NULL,
            applied_at DATETIME(3) NOT NULL,
            PRIMARY KEY (version)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
        (),
    )


async def migration_was_applied(
    repository: MySQLChatRepository,
    migration: DatabaseV2Migration,
) -> bool:
    row = await repository._fetchone(
        """
        SELECT version
        FROM schema_migrations
        WHERE version = %s
        LIMIT 1
        """,
        (migration.version,),
    )
    return row is not None


async def record_migration(
    repository: MySQLChatRepository,
    migration: DatabaseV2Migration,
) -> None:
    await repository._execute(
        """
        INSERT INTO schema_migrations (version, description, applied_at)
        VALUES (%s, %s, %s)
        """,
        (
            migration.version,
            migration.description,
            dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        ),
    )


async def apply_migration(
    repository: MySQLChatRepository,
    migration: DatabaseV2Migration,
) -> bool:
    if await migration_was_applied(repository, migration):
        return False
    sql = migration.path.read_text(encoding="utf-8")
    for statement in split_sql_statements(sql):
        await repository._execute(statement, ())
    # Older V2 migration files record their own version while the first schema
    # migration does not.  Re-checking prevents a duplicate primary-key insert.
    if not await migration_was_applied(repository, migration):
        await record_migration(repository, migration)
    return True


async def apply_pending_migrations(
    *,
    repository: MySQLChatRepository,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[str]:
    await ensure_schema_migrations_table(repository)
    applied: list[str] = []
    for migration in discover_migrations(migrations_dir):
        if await apply_migration(repository, migration):
            applied.append(migration.version)
    return applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply HutaoChatCore database v2 migrations.")
    parser.add_argument(
        "--migrations-dir",
        default=str(MIGRATIONS_DIR),
        help="Directory containing v2 SQL migrations.",
    )
    parser.add_argument(
        "--allow-non-hutao-chat-core",
        action="store_true",
        help="Allow applying V2 migrations to a non-hutao_chat_core test database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    validate_target_database(
        settings.mysql_database,
        allow_non_target=args.allow_non_hutao_chat_core,
    )
    repository = MySQLChatRepository(settings)
    applied = asyncio.run(
        apply_pending_migrations(
            repository=repository,
            migrations_dir=Path(args.migrations_dir),
        )
    )
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("No pending database v2 migrations.")


if __name__ == "__main__":
    main()
