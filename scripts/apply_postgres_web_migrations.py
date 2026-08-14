from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    # psycopg async requires a selector-based event loop (see app/main.py).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.storage.chat_repository import utc_now
from app.storage.postgres_repository import PostgreSQLChatRepository


MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "postgres"


@dataclass(frozen=True)
class PostgreSQLMigration:
    version: str
    description: str
    path: Path


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[PostgreSQLMigration]:
    return [
        PostgreSQLMigration(
            version="postgres." + path.stem,
            description=path.stem.replace("_", " "),
            path=path,
        )
        for path in sorted(migrations_dir.glob("*.sql"))
    ]


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for raw_line in sql.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        current.append(raw_line)
        if line.endswith(";"):
            statements.append("\n".join(current).strip()[:-1].strip())
            current = []
    if current:
        statements.append("\n".join(current).strip())
    return statements


async def ensure_schema_migrations_table(repository: PostgreSQLChatRepository) -> None:
    await repository._execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(128) PRIMARY KEY,
            description VARCHAR(255) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL
        )
        """,
        (),
    )


async def migration_was_applied(
    repository: PostgreSQLChatRepository, migration: PostgreSQLMigration
) -> bool:
    row = await repository._fetchone(
        "SELECT version FROM schema_migrations WHERE version = %s LIMIT 1",
        (migration.version,),
    )
    return row is not None


async def apply_pending_migrations(
    repository: PostgreSQLChatRepository,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[str]:
    await ensure_schema_migrations_table(repository)
    applied: list[str] = []
    for migration in discover_migrations(migrations_dir):
        if await migration_was_applied(repository, migration):
            continue
        for statement in split_sql_statements(migration.path.read_text(encoding="utf-8")):
            await repository._execute(statement, ())
        await repository._execute(
            """
            INSERT INTO schema_migrations (version, description, applied_at)
            VALUES (%s, %s, %s)
            """,
            (migration.version, migration.description, utc_now()),
        )
        applied.append(migration.version)
    return applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply HutaoChatCore PostgreSQL web-core migrations.")
    parser.add_argument("--dry-run", action="store_true", help="List migrations without connecting.")
    parser.add_argument(
        "--migrations-dir",
        default=str(MIGRATIONS_DIR),
        help="Directory containing PostgreSQL migration files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    migrations_dir = Path(args.migrations_dir)
    migrations = discover_migrations(migrations_dir)
    if args.dry_run:
        for migration in migrations:
            print(migration.version)
        return

    settings = load_settings()
    if settings.storage_backend.strip().lower() not in {"postgres", "postgresql"}:
        raise SystemExit("Set STORAGE_BACKEND=postgresql before applying PostgreSQL migrations.")
    applied = asyncio.run(apply_pending_migrations(PostgreSQLChatRepository(settings), migrations_dir))
    print("Applied migrations: " + ", ".join(applied) if applied else "No pending PostgreSQL migrations.")


if __name__ == "__main__":
    main()
