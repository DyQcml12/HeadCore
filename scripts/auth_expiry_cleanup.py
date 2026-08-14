from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import load_settings
from app.storage.mysql_repository import mysql_datetime
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository


EXPIRY_CLEANUP_TARGETS: tuple[tuple[str, str], ...] = (
    ("web_sessions", "DELETE FROM web_sessions WHERE expires_at < %s"),
    ("email_verification_tokens", "DELETE FROM email_verification_tokens WHERE expires_at < %s"),
    ("password_reset_tokens", "DELETE FROM password_reset_tokens WHERE expires_at < %s OR used_at IS NOT NULL"),
    ("registration_attempts", "DELETE FROM registration_attempts WHERE window_started_at < %s"),
)


def build_expiry_cleanup_queries(now: datetime) -> list[tuple[str, str, str]]:
    """Return (label, count_sql, delete_sql) for every cleanup target."""
    timestamp = mysql_datetime(now.isoformat())
    queries: list[tuple[str, str, str]] = []
    for label, delete_sql in EXPIRY_CLEANUP_TARGETS:
        table = label
        count_sql = "SELECT COUNT(*) FROM " + table + " WHERE " + delete_sql.split(" WHERE ", 1)[1].replace("%s", "%s")
        queries.append((label, count_sql, delete_sql))
    return queries


async def run_cleanup(repository, *, now: datetime, dry_run: bool) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    timestamp = mysql_datetime(now.isoformat())
    for label, count_sql, delete_sql in build_expiry_cleanup_queries(now):
        try:
            if dry_run:
                row = await repository._fetchone(count_sql, (timestamp,))
                count = int(next(iter(row.values()))) if row else 0
                items.append({"table": label, "would_delete": count})
            else:
                affected = await repository._execute(delete_sql, (timestamp,))
                items.append({"table": label, "deleted": affected})
        except Exception as exc:
            items.append({"table": label, "error": type(exc).__name__})
    return {"status": "OK", "dry_run": dry_run, "items": items}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean expired public-web auth rows.")
    parser.add_argument("--apply", action="store_true", help="Actually delete rows; default is dry-run.")
    parser.add_argument("--older-than-hours", type=int, default=24, help="Only touch rows older than N hours (default 24).")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    if not all((settings.mysql_database, settings.mysql_user, settings.mysql_password)):
        print(json.dumps({"status": "SKIP", "reason": "MYSQL_DATABASE/MYSQL_USER/MYSQL_PASSWORD not configured"}, ensure_ascii=False, indent=2))
        return 0
    now = datetime.now(timezone.utc) - timedelta(hours=args.older_than_hours)
    repository = MySQLDatabaseV2Repository(settings)
    result = asyncio.run(run_cleanup(repository, now=now, dry_run=not args.apply))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
