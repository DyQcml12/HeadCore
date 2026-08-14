from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository, legacy_role_to_v2_relationship
from scripts.apply_database_v2_migrations import validate_target_database


LEGACY_JSONL_FILES = {
    "sessions": "sessions.jsonl",
    "messages": "messages.jsonl",
    "model_invocations": "model_invocations.jsonl",
    "persona_evaluations": "persona_evaluations.jsonl",
    "memories": "memories.jsonl",
    "contacts": "contacts.jsonl",
    "platform_identities": "platform_identities.jsonl",
    "relationship_claims": "relationship_claims.jsonl",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if isinstance(item, dict):
            rows.append(item)
    return rows


def load_legacy_jsonl_snapshot(storage_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        key: read_jsonl(storage_dir / filename)
        for key, filename in LEGACY_JSONL_FILES.items()
    }


def summarize_snapshot(snapshot: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    summary = {key: len(rows) for key, rows in snapshot.items()}
    summary["legacy_owner_contacts"] = sum(
        1
        for row in snapshot.get("contacts", [])
        if legacy_role_to_v2_relationship(str(row.get("relationship_role") or "")) == "admin_partner"
    )
    summary["legacy_blocked_contacts"] = sum(
        1
        for row in snapshot.get("contacts", [])
        if legacy_role_to_v2_relationship(str(row.get("relationship_role") or "")) == "blocked"
    )
    summary["legacy_normal_contacts"] = sum(
        1
        for row in snapshot.get("contacts", [])
        if legacy_role_to_v2_relationship(str(row.get("relationship_role") or "")) == "normal_friend"
    )
    return summary


async def migrate_legacy_jsonl_to_database_v2(
    *,
    repository: MySQLDatabaseV2Repository,
    storage_dir: Path,
    dry_run: bool = True,
) -> dict[str, int]:
    snapshot = load_legacy_jsonl_snapshot(storage_dir)
    summary = summarize_snapshot(snapshot)
    if dry_run:
        return {"dry_run": 1, **summary}
    imported = await repository.import_legacy_jsonl_snapshot(snapshot=snapshot)
    return {"dry_run": 0, **summary, **{"imported_" + key: value for key, value in imported.items()}}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy JSONL storage into database V2.")
    parser.add_argument(
        "--storage-dir",
        default=str(PROJECT_ROOT / "logs" / "storage"),
        help="Legacy JSONL storage directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write records into MySQL. Omit for dry-run summary only.",
    )
    parser.add_argument(
        "--allow-non-hutao-chat-core",
        action="store_true",
        help="Allow writing to a non-hutao_chat_core test database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    storage_dir = Path(args.storage_dir)
    if not args.apply:
        result = {"dry_run": 1, **summarize_snapshot(load_legacy_jsonl_snapshot(storage_dir))}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return

    if args.apply:
        validate_target_database(
            settings.mysql_database,
            allow_non_target=args.allow_non_hutao_chat_core,
        )
    repository = MySQLDatabaseV2Repository(settings)
    result = asyncio.run(
        migrate_legacy_jsonl_to_database_v2(
            repository=repository,
            storage_dir=storage_dir,
            dry_run=False,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
