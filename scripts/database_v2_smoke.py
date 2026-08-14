from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, Settings, load_settings
from app.core.security import redact_secrets
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository
from app.storage.v2_platform_command_service import DatabaseV2PlatformCommandService
from app.storage.v2_relationship_service import DatabaseV2RelationshipService, PlatformIdentity, parse_bootstrap_ids
from app.storage.v2_runtime import database_v2_chat_user_id
from scripts.database_v2_readiness_check import check_database_v2_readiness


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "database-v2-smoke"
DEFAULT_USER_INPUT = "数据库 V2 冒烟测试：普通聊天写入。"
DEFAULT_REPLY = "收到，数据库 V2 冒烟测试回复。"
REQUIRED_MYSQL_SETTINGS = ["mysql_database", "mysql_user", "mysql_password"]


class DatabaseV2SmokeClient:
    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        return DEFAULT_REPLY


async def run_database_v2_smoke(
    *,
    platform: str,
    platform_user_id: str,
    platform_group_id: str | None,
    user_input: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    require_enabled: bool = True,
    allow_non_target: bool = False,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "database-v2-smoke-report.md"
    json_path = output_dir / "database-v2-smoke-result.json"

    settings = load_settings()
    missing = [name.upper() for name in REQUIRED_MYSQL_SETTINGS if not getattr(settings, name)]
    if missing:
        data = {
            "status": "SKIP",
            "reason": "missing MySQL settings: " + ", ".join(missing),
            "platform": platform,
            "platform_user_id": platform_user_id,
        }
        write_smoke_result(json_path=json_path, report_path=report_path, data=data, started_at=started_at)
        return report_path

    repository = MySQLDatabaseV2Repository(settings)
    status = "PASS"
    error = None
    readiness: dict[str, object] | None = None
    response_data: dict[str, Any] | None = None
    row_counts: dict[str, int] = {}
    command_data: dict[str, object] | None = None
    try:
        readiness_result = await check_database_v2_readiness(
            repository=repository,
            settings=settings,
            require_enabled=require_enabled,
            allow_non_target=allow_non_target,
        )
        readiness = readiness_result.to_dict()
        if readiness_result.status != "PASS":
            status = "FAIL"
            error = "database v2 readiness check failed"
        else:
            relationship_service = DatabaseV2RelationshipService(repository)
            await relationship_service.bootstrap_admin_from_settings(settings)
            session_token = build_smoke_session_token(
                platform=platform,
                platform_user_id=platform_user_id,
                timestamp=timestamp,
            )
            chat_user_id = database_v2_chat_user_id(
                platform=platform,
                platform_user_id=platform_user_id,
                fallback_user_id="database-v2-smoke-user",
            )
            response = await ChatService(
                settings,
                client=DatabaseV2SmokeClient(),
                audit_logger=ModelInvocationAuditLogger(output_dir / "audit.jsonl"),
                repository=repository,
            ).reply(
                user_input,
                session_id=session_token,
                user_id=chat_user_id,
                platform=platform,
                platform_user_id=platform_user_id,
                platform_group_id=platform_group_id,
            )
            response_data = response.model_dump()
            row_counts = await count_database_v2_smoke_rows(
                repository=repository,
                platform=platform,
                session_token=session_token,
            )
            if not smoke_row_counts_pass(row_counts):
                status = "FAIL"
                error = f"unexpected database v2 row counts: {row_counts}"

            command_data = await run_optional_admin_command_smoke(
                repository=repository,
                settings=settings,
                platform=platform,
                target_platform_user_id=platform_user_id,
            )
            if command_data.get("status") == "FAIL":
                status = "FAIL"
                error = str(command_data.get("error") or "admin command smoke failed")
    except Exception as exc:
        status = "FAIL"
        error = redact_secrets(str(exc))

    data = {
        "status": status,
        "platform": platform,
        "platform_user_id": platform_user_id,
        "platform_group_id": platform_group_id,
        "readiness": readiness,
        "response": response_data,
        "row_counts": row_counts,
        "admin_command": command_data,
        "error": error,
    }
    write_smoke_result(json_path=json_path, report_path=report_path, data=data, started_at=started_at)
    return report_path


def build_smoke_session_token(*, platform: str, platform_user_id: str, timestamp: str) -> str:
    return f"database-v2-smoke-{platform}-{platform_user_id}-{timestamp}"


async def count_database_v2_smoke_rows(
    *,
    repository: MySQLDatabaseV2Repository,
    platform: str,
    session_token: str,
) -> dict[str, int]:
    conversation = await repository._fetchone(
        """
        SELECT id
        FROM conversations
        WHERE platform = %s
          AND platform_thread_id = %s
        LIMIT 1
        """,
        (platform, session_token),
    )
    if conversation is None:
        return {
            "conversations": 0,
            "messages": 0,
            "model_invocations": 0,
            "persona_evaluations": 0,
        }
    conversation_id = str(conversation["id"])
    messages = await count_rows(
        repository,
        "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = %s",
        (conversation_id,),
    )
    invocations = await count_rows(
        repository,
        "SELECT COUNT(*) AS count FROM model_invocations WHERE conversation_id = %s",
        (conversation_id,),
    )
    evaluations = await count_rows(
        repository,
        """
        SELECT COUNT(*) AS count
        FROM persona_evaluations pe
        INNER JOIN messages m ON m.id = pe.message_id
        WHERE m.conversation_id = %s
        """,
        (conversation_id,),
    )
    return {
        "conversations": 1,
        "messages": messages,
        "model_invocations": invocations,
        "persona_evaluations": evaluations,
    }


async def count_rows(
    repository: MySQLDatabaseV2Repository,
    sql: str,
    params: tuple[Any, ...],
) -> int:
    row = await repository._fetchone(sql, params)
    return int(row["count"]) if row else 0


def smoke_row_counts_pass(row_counts: dict[str, int]) -> bool:
    return row_counts == {
        "conversations": 1,
        "messages": 2,
        "model_invocations": 1,
        "persona_evaluations": 1,
    }


async def run_optional_admin_command_smoke(
    *,
    repository: MySQLDatabaseV2Repository,
    settings: Settings,
    platform: str,
    target_platform_user_id: str,
) -> dict[str, object]:
    admin_user_id = first_bootstrap_id(settings, platform=platform)
    if not admin_user_id:
        return {
            "status": "SKIP",
            "reason": f"no bootstrap admin id configured for platform={platform}",
        }
    relationship_service = DatabaseV2RelationshipService(repository)
    command_service = DatabaseV2PlatformCommandService(
        relationship_service=relationship_service,
        repository=repository,
    )
    result = await command_service.handle_message(
        identity=PlatformIdentity(
            platform=platform,  # type: ignore[arg-type]
            platform_user_id=admin_user_id,
            conversation_type="private",
        ),
        message_text=f"查看关系 {platform} {target_platform_user_id}",
        message_id=None,
    )
    return {
        "status": "PASS" if result.execution_result and result.execution_result.executed else "FAIL",
        "reason_code": result.reason_code,
        "payload": result.to_adapter_payload(),
    }


def first_bootstrap_id(settings: Settings, *, platform: str) -> str:
    if platform == "qq":
        ids = parse_bootstrap_ids(settings.owner_bootstrap_qq_ids)
    elif platform == "wechat":
        ids = parse_bootstrap_ids(settings.owner_bootstrap_wechat_ids)
    else:
        ids = []
    return ids[0] if ids else ""


def write_smoke_result(
    *,
    json_path: Path,
    report_path: Path,
    data: dict[str, Any],
    started_at: dt.datetime,
) -> None:
    finished_at = dt.datetime.now()
    safe_json = redact_secrets(json.dumps(data, ensure_ascii=False, indent=2))
    json_path.write_text(safe_json, encoding="utf-8")
    report = "\n".join(
        [
            "# Database V2 Smoke Report",
            "",
            f"- Result: {data['status']}",
            f"- Started at: {started_at.isoformat(timespec='seconds')}",
            f"- Finished at: {finished_at.isoformat(timespec='seconds')}",
            f"- Platform: {data.get('platform')}",
            f"- Platform user id: {data.get('platform_user_id')}",
            f"- Raw JSON: `{json_path}`",
            "",
            "## Summary",
            "",
            format_smoke_summary(data),
            "",
            "## Raw Result",
            "",
            "```json",
            safe_json,
            "```",
            "",
        ]
    )
    report_path.write_text(redact_secrets(report), encoding="utf-8")


def format_smoke_summary(data: dict[str, Any]) -> str:
    lines = []
    if data.get("reason"):
        lines.append(f"- Skip reason: {data['reason']}")
    rows = data.get("row_counts")
    if isinstance(rows, dict):
        lines.append(f"- Conversations: {rows.get('conversations', 0)}")
        lines.append(f"- Messages: {rows.get('messages', 0)}")
        lines.append(f"- Model invocations: {rows.get('model_invocations', 0)}")
        lines.append(f"- Persona evaluations: {rows.get('persona_evaluations', 0)}")
    command = data.get("admin_command")
    if isinstance(command, dict):
        lines.append(f"- Admin command: {command.get('status')} ({command.get('reason_code') or command.get('reason')})")
    if data.get("error"):
        lines.append(f"- Error: {data['error']}")
    return "\n".join(lines) if lines else "- No details."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a real Database V2 MySQL smoke test.")
    parser.add_argument("--platform", choices=["qq", "wechat"], default="qq")
    parser.add_argument("--platform-user-id", required=True)
    parser.add_argument("--platform-group-id", default=None)
    parser.add_argument("--user-input", default=DEFAULT_USER_INPUT)
    parser.add_argument(
        "--allow-disabled",
        action="store_true",
        help="Allow DATABASE_V2_ENABLED=false for direct database smoke testing.",
    )
    parser.add_argument(
        "--allow-non-hutao-chat-core",
        action="store_true",
        help="Allow smoking a non-hutao_chat_core test database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path = asyncio.run(
        run_database_v2_smoke(
            platform=args.platform,
            platform_user_id=args.platform_user_id,
            platform_group_id=args.platform_group_id,
            user_input=args.user_input,
            require_enabled=not args.allow_disabled,
            allow_non_target=args.allow_non_hutao_chat_core,
        )
    )
    print(f"Database V2 smoke report: {report_path}")


if __name__ == "__main__":
    main()
