from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import Settings, load_settings
from app.core.security import redact_secrets
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository
from app.storage.v2_relationship_service import parse_bootstrap_ids
from app.storage.v2_repository import DATABASE_V2_SCHEMA_VERSION
from scripts.apply_database_v2_migrations import validate_target_database


REQUIRED_V2_TABLES = (
    "schema_migrations",
    "personas",
    "persona_versions",
    "profiles",
    "admin_profile",
    "platform_accounts",
    "persona_runtime_bindings",
    "profile_social_labels",
    "relationship_events",
    "relationship_pending_claims",
    "profile_portraits",
    "admin_private_profile",
    "profile_emotional_state",
    "conversations",
    "messages",
    "message_attachments",
    "model_invocations",
    "conversation_persona_state",
    "persona_evaluations",
    "safety_guard_events",
    "memories",
    "memory_events",
    "qq_inbound_events",
    "qq_outbound_events",
    "wechat_inbound_events",
    "wechat_outbound_events",
    "platform_command_events",
)


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DatabaseV2ReadinessResult:
    status: str
    checks: list[ReadinessCheck]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "checks": [asdict(check) for check in self.checks],
        }


async def check_database_v2_readiness(
    *,
    repository: MySQLDatabaseV2Repository,
    settings: Settings,
    require_enabled: bool = True,
    allow_non_target: bool = False,
) -> DatabaseV2ReadinessResult:
    checks: list[ReadinessCheck] = []

    checks.append(check_target_database(settings, allow_non_target=allow_non_target))
    checks.append(check_v2_enabled(settings, require_enabled=require_enabled))
    checks.append(await check_schema_version(repository))
    checks.extend(await check_required_tables(repository, settings.mysql_database))
    checks.append(await check_admin_bootstrap_or_existing_admin(repository, settings))

    status = "PASS" if all(check.passed for check in checks) else "FAIL"
    return DatabaseV2ReadinessResult(status=status, checks=checks)


def check_target_database(settings: Settings, *, allow_non_target: bool) -> ReadinessCheck:
    try:
        validate_target_database(settings.mysql_database, allow_non_target=allow_non_target)
    except ValueError as exc:
        return ReadinessCheck(
            name="target_database",
            passed=False,
            detail=str(exc),
        )
    return ReadinessCheck(
        name="target_database",
        passed=True,
        detail=f"MYSQL_DATABASE={settings.mysql_database}",
    )


def check_v2_enabled(settings: Settings, *, require_enabled: bool) -> ReadinessCheck:
    if settings.database_v2_enabled:
        return ReadinessCheck("database_v2_enabled", True, "DATABASE_V2_ENABLED=true")
    return ReadinessCheck(
        "database_v2_enabled",
        not require_enabled,
        "DATABASE_V2_ENABLED=false",
    )


async def check_schema_version(repository: MySQLDatabaseV2Repository) -> ReadinessCheck:
    row = await repository._fetchone(
        """
        SELECT version
        FROM schema_migrations
        WHERE version = %s
        LIMIT 1
        """,
        (DATABASE_V2_SCHEMA_VERSION,),
    )
    if row is None:
        return ReadinessCheck(
            "schema_version",
            False,
            f"missing {DATABASE_V2_SCHEMA_VERSION}",
        )
    return ReadinessCheck(
        "schema_version",
        True,
        f"found {DATABASE_V2_SCHEMA_VERSION}",
    )


async def check_required_tables(
    repository: MySQLDatabaseV2Repository,
    database_name: str,
) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    for table_name in REQUIRED_V2_TABLES:
        row = await repository._fetchone(
            """
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
            LIMIT 1
            """,
            (database_name, table_name),
        )
        checks.append(
            ReadinessCheck(
                name=f"table:{table_name}",
                passed=row is not None,
                detail="found" if row is not None else "missing",
            )
        )
    return checks


async def check_admin_bootstrap_or_existing_admin(
    repository: MySQLDatabaseV2Repository,
    settings: Settings,
) -> ReadinessCheck:
    row = await repository._fetchone(
        """
        SELECT profile_id
        FROM admin_profile
        WHERE singleton_id = 1
        LIMIT 1
        """,
        (),
    )
    if row is not None:
        return ReadinessCheck("admin_profile", True, "existing singleton admin")

    qq_ids = parse_bootstrap_ids(settings.owner_bootstrap_qq_ids)
    wechat_ids = parse_bootstrap_ids(settings.owner_bootstrap_wechat_ids)
    if qq_ids or wechat_ids:
        return ReadinessCheck(
            "admin_profile",
            True,
            "no admin yet, bootstrap ids configured",
        )
    return ReadinessCheck(
        "admin_profile",
        False,
        "no existing admin and no OWNER_BOOTSTRAP_QQ_IDS/OWNER_BOOTSTRAP_WECHAT_IDS",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Database V2 readiness before enabling runtime.")
    parser.add_argument(
        "--allow-disabled",
        action="store_true",
        help="Do not fail when DATABASE_V2_ENABLED=false.",
    )
    parser.add_argument(
        "--allow-non-hutao-chat-core",
        action="store_true",
        help="Allow checks against a non-hutao_chat_core test database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    repository = MySQLDatabaseV2Repository(settings)
    result = asyncio.run(
        check_database_v2_readiness(
            repository=repository,
            settings=settings,
            require_enabled=not args.allow_disabled,
            allow_non_target=args.allow_non_hutao_chat_core,
        )
    )
    print(redact_secrets(json.dumps(result.to_dict(), ensure_ascii=False, indent=2)))
    if result.status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
