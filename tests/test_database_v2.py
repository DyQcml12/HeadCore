from __future__ import annotations

import asyncio
import re
from pathlib import Path

from app.core.config import load_settings
from app.storage.v2_command_executor import execute_v2_admin_command
from app.storage.v2_command_policy import (
    decide_v2_admin_command,
    parse_v2_admin_command,
)
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository
from app.storage.v2_platform_command_service import (
    DatabaseV2PlatformCommandService,
    normalize_platform_command_text,
)
from app.storage.v2_models import (
    V2ChatMessage,
    V2PendingRelationshipClaim,
    V2PlatformAccount,
    V2Profile,
    V2RecentChat,
    build_relationship_context,
    fallback_persona_context,
    normalize_platform_group_id,
    normalize_relationship_type,
    permissions_for_relationship,
)
from app.storage.v2_relationship_service import (
    DatabaseV2RelationshipService,
    PlatformIdentity,
    parse_bootstrap_ids,
)
from app.storage.v2_runtime import should_use_database_v2
from app.storage.v2_repository import (
    DATABASE_V2_SCHEMA_DESCRIPTION,
    DATABASE_V2_SCHEMA_VERSION,
)
from scripts.apply_database_v2_migrations import (
    DatabaseV2Migration,
    apply_pending_migrations,
    discover_migrations,
    split_sql_statements,
    validate_target_database,
)
from scripts.migrate_jsonl_to_database_v2 import (
    load_legacy_jsonl_snapshot,
    migrate_legacy_jsonl_to_database_v2,
    summarize_snapshot,
)
from scripts.database_v2_readiness_check import (
    REQUIRED_V2_TABLES,
    check_database_v2_readiness,
)
from scripts.database_v2_smoke import (
    count_database_v2_smoke_rows,
    first_bootstrap_id,
    smoke_row_counts_pass,
)


class RecordingV2MigrationRepository:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.applied_versions: set[str] = set()

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:
        self.statements.append((sql, params))
        if "INSERT INTO schema_migrations" in sql and params:
            self.applied_versions.add(str(params[0]))
        elif "INSERT INTO schema_migrations" in sql:
            version = re.search(r"VALUES\s*\(\s*'([^']+)'", sql, flags=re.IGNORECASE)
            if version is not None:
                self.applied_versions.add(version.group(1))
        return 1

    async def _fetchone(
        self,
        sql: str,
        params: tuple[object, ...],
    ) -> dict[str, object] | None:
        self.statements.append((sql, params))
        version = str(params[0]) if params else ""
        if version in self.applied_versions:
            return {"version": version}
        return None


class RecordingMySQLDatabaseV2Repository(MySQLDatabaseV2Repository):
    def __init__(self) -> None:
        settings = load_settings()
        object.__setattr__(settings, "mysql_database", "hutao_chat_core")
        object.__setattr__(settings, "mysql_user", "hutao_user")
        object.__setattr__(settings, "mysql_password", "password-from-env")
        super().__init__(settings)
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.fetchone_results: list[dict[str, object] | None] = []
        self.fetchall_results: list[list[dict[str, object]]] = []

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:
        self.statements.append((sql, params))
        return 1

    async def _fetchone(
        self,
        sql: str,
        params: tuple[object, ...],
    ) -> dict[str, object] | None:
        self.statements.append((sql, params))
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    async def _fetchall(
        self,
        sql: str,
        params: tuple[object, ...],
    ) -> list[dict[str, object]]:
        self.statements.append((sql, params))
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []

    async def _execute_transaction(
        self, statements: list[tuple[str, tuple[object, ...]]]
    ) -> None:
        self.statements.extend(statements)


class FakeDatabaseV2Repository:
    def __init__(self, relationship_type: str = "normal_friend", account_status: str = "active") -> None:
        self.bootstrap_args: dict[str, object] | None = None
        self.resolve_args: dict[str, object] | None = None
        self.context = build_relationship_context(
            profile=V2Profile(
                id="profile-1",
                display_name="测试用户",
                relationship_type=normalize_relationship_type(relationship_type),
                verified=relationship_type == "admin_partner",
                trust_level=100 if relationship_type == "admin_partner" else 10,
                affection_level=100 if relationship_type == "admin_partner" else 10,
                notes="",
                status="active",
                merged_into_profile_id=None,
                created_at="2026-07-06 19:00:00.000",
                updated_at="2026-07-06 19:00:00.000",
            ),
            platform_account=V2PlatformAccount(
                id="account-1",
                profile_id="profile-1",
                platform="qq",
                platform_user_id="10001",
                platform_group_id="",
                display_name="平台昵称",
                account_label="unknown",
                is_primary=True,
                status=account_status,  # type: ignore[arg-type]
                confidence=50,
                verified_by_profile_id=None,
                last_seen_at=None,
                created_at="2026-07-06 19:00:00.000",
                updated_at="2026-07-06 19:00:00.000",
            ),
            social_labels=("friend:测试",),
        )

    async def bootstrap_admin_if_missing(
        self,
        *,
        qq_ids: list[str],
        wechat_ids: list[str],
        display_name: str,
    ) -> str | None:
        self.bootstrap_args = {
            "qq_ids": qq_ids,
            "wechat_ids": wechat_ids,
            "display_name": display_name,
        }
        return "profile-admin"

    async def resolve_relationship_context(
        self,
        *,
        platform: str,
        platform_user_id: str,
        platform_group_id: str | None = None,
        display_name: str = "",
    ):
        self.resolve_args = {
            "platform": platform,
            "platform_user_id": platform_user_id,
            "platform_group_id": platform_group_id,
            "display_name": display_name,
        }
        return self.context

    async def ensure_default_personas(self) -> None:
        return None

    async def resolve_persona_context(self, **_kwargs):
        return fallback_persona_context(self.context.effective_relationship_type)

    async def set_relationship(self, **_kwargs):  # pragma: no cover - not used by these tests
        return self.context

    async def bind_accounts(self, **_kwargs):  # pragma: no cover - not used by these tests
        return "profile-1"

    async def list_recent_chats(self, *, limit: int = 10):
        return []

    async def list_chat_history(self, **_kwargs):
        return []

    async def list_pending_relationship_claims(self, *, limit: int = 20):
        return []

    async def approve_relationship_claim(self, **_kwargs):
        return {"status": "approved"}

    async def reject_relationship_claim(self, **_kwargs):
        return {"status": "rejected"}

    async def record_platform_command_event(self, **_kwargs) -> None:
        return None


class ExecutingFakeDatabaseV2Repository(FakeDatabaseV2Repository):
    def __init__(self, relationship_type: str = "admin_partner", account_status: str = "active") -> None:
        super().__init__(relationship_type=relationship_type, account_status=account_status)
        self.set_relationship_calls: list[dict[str, object]] = []
        self.bind_accounts_calls: list[dict[str, object]] = []
        self.chat_history_calls: list[dict[str, object]] = []
        self.approve_claim_calls: list[dict[str, object]] = []
        self.reject_claim_calls: list[dict[str, object]] = []
        self.command_events: list[dict[str, object]] = []

    async def set_relationship(self, **kwargs):
        self.set_relationship_calls.append(kwargs)
        relationship_type = str(kwargs["relationship_type"])
        self.context = build_relationship_context(
            profile=V2Profile(
                id=self.context.profile.id,
                display_name=kwargs.get("display_name") or self.context.profile.display_name,
                relationship_type=normalize_relationship_type(relationship_type),
                verified=relationship_type == "admin_partner" or self.context.profile.verified,
                trust_level=100 if relationship_type == "admin_partner" else 10,
                affection_level=100 if relationship_type == "admin_partner" else 10,
                notes="",
                status="active",
                merged_into_profile_id=None,
                created_at=self.context.profile.created_at,
                updated_at=self.context.profile.updated_at,
            ),
            platform_account=self.context.platform_account,
            social_labels=self.context.social_labels,
        )
        return self.context

    async def bind_accounts(self, **kwargs):
        self.bind_accounts_calls.append(kwargs)
        return "profile-bound"

    async def list_recent_chats(self, *, limit: int = 10):
        return [
            V2RecentChat(
                conversation_id="conversation-1",
                platform="qq",
                conversation_type="private",
                platform_thread_id="123456",
                title="张三",
                owner_profile_id="profile-friend",
                owner_display_name="张三",
                owner_relationship_type="normal_friend",
                last_message_at="2026-07-06 20:00:00.000",
                message_count=3,
            )
        ]

    async def list_chat_history(self, **kwargs):
        self.chat_history_calls.append(kwargs)
        return [
            V2ChatMessage(
                id="message-1",
                conversation_id="conversation-1",
                profile_id="profile-friend",
                platform_account_id="account-friend",
                platform="qq",
                platform_message_id="msg-1",
                direction="inbound",
                role="user",
                content_type="text",
                content="你好",
                safety_status="passed",
                memory_eligible=False,
                visible_to_admin=True,
                created_at="2026-07-06 20:00:00.000",
                conversation_title="张三",
            )
        ]

    async def list_pending_relationship_claims(self, *, limit: int = 20):
        return [
            V2PendingRelationshipClaim(
                id="claim-1",
                platform="qq",
                platform_user_id="123456",
                claimed_name="张三",
                claimed_relation_text="我是你的同学",
                status="pending",
                reviewed_by_profile_id=None,
                created_at="2026-07-06 20:00:00.000",
                reviewed_at=None,
            )
        ]

    async def approve_relationship_claim(self, **kwargs):
        self.approve_claim_calls.append(kwargs)
        return {
            "status": "approved",
            "claim_id": kwargs["claim_id"],
            "profile_id": "profile-friend",
            "relationship_type": "normal_friend",
        }

    async def reject_relationship_claim(self, **kwargs):
        self.reject_claim_calls.append(kwargs)
        return {"status": "rejected", "claim_id": kwargs["claim_id"]}

    async def record_platform_command_event(self, **kwargs) -> None:
        self.command_events.append(kwargs)


def profile_account_row(
    *,
    profile_id: str = "profile-1",
    account_id: str = "account-1",
    relationship_type: str = "normal_friend",
    verified: bool = False,
    account_status: str = "active",
    platform: str = "qq",
    platform_user_id: str = "10001",
    platform_group_id: str = "",
) -> dict[str, object]:
    return {
        "id": profile_id,
        "display_name": "测试用户",
        "relationship_type": relationship_type,
        "verified": verified,
        "trust_level": 10 if relationship_type == "normal_friend" else 100,
        "affection_level": 10 if relationship_type == "normal_friend" else 100,
        "notes": "",
        "status": "active",
        "merged_into_profile_id": None,
        "created_at": "2026-07-06 19:00:00.000",
        "updated_at": "2026-07-06 19:00:00.000",
        "account_id": account_id,
        "profile_id": profile_id,
        "platform": platform,
        "platform_user_id": platform_user_id,
        "platform_group_id": platform_group_id,
        "account_display_name": "平台昵称",
        "account_label": "unknown",
        "is_primary": True,
        "account_status": account_status,
        "confidence": 50,
        "verified_by_profile_id": None,
        "last_seen_at": "2026-07-06 19:00:00.000",
        "account_created_at": "2026-07-06 19:00:00.000",
        "account_updated_at": "2026-07-06 19:00:00.000",
    }


def conversation_row(
    *,
    conversation_id: str = "conversation-1",
    platform: str = "qq",
    conversation_type: str = "private",
    platform_thread_id: str = "qq-private-123456",
    owner_profile_id: str = "profile-friend",
) -> dict[str, object]:
    return {
        "id": conversation_id,
        "platform": platform,
        "conversation_type": conversation_type,
        "platform_thread_id": platform_thread_id,
        "owner_profile_id": owner_profile_id,
        "title": platform_thread_id,
        "created_at": "2026-07-07 01:00:00.000",
        "updated_at": "2026-07-07 01:00:00.000",
    }


def persona_row(
    *,
    persona_id: str = "persona-1",
    code: str = "hutao_v1",
    display_name: str = "胡桃",
    source_scope: str | None = None,
    state_json: str | None = None,
) -> dict[str, object]:
    return {
        "persona_id": persona_id,
        "persona_code": code,
        "persona_display_name": display_name,
        "persona_description": "test persona",
        "persona_status": "active",
        "default_for_admin": code == "hutao_v1",
        "default_for_normal_friend": code == "hutao_v1",
        "persona_created_at": "2026-07-07 01:00:00.000",
        "persona_updated_at": "2026-07-07 01:00:00.000",
        "persona_version_id": "persona-version-1",
        "version_label": "initial",
        "prompt_template": "test prompt",
        "style_rules_json": '{"reply_length":"short"}',
        "safety_rules_json": "{}",
        "memory_policy_json": "{}",
        "version_active": True,
        "created_by_profile_id": None,
        "version_created_at": "2026-07-07 01:00:00.000",
        "binding_scope": source_scope,
        "state_json": state_json,
    }


def test_database_v2_schema_contains_core_identity_and_chat_tables() -> None:
    project_root = Path(__file__).resolve().parents[1]
    schema = (project_root / "migrations" / "v2" / "001_hutao_chat_core_schema.sql").read_text(
        encoding="utf-8"
    )

    for table_name in [
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
        "conversation_persona_state",
        "messages",
        "message_attachments",
        "model_invocations",
        "persona_evaluations",
        "safety_guard_events",
        "memories",
        "memory_events",
        "qq_inbound_events",
        "qq_outbound_events",
        "wechat_inbound_events",
        "wechat_outbound_events",
        "platform_command_events",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in schema

    assert "admin_partner" in schema
    assert "normal_friend" in schema
    assert "blocked" in schema
    assert "persona_id CHAR(36) NULL" in schema
    assert "visibility_scope ENUM('admin_private', 'profile_private', 'persona_specific', 'safe_preference')" in schema
    assert "owner_friend" not in schema
    assert "owner_relative" not in schema
    assert "stranger" not in schema


def test_database_v2_schema_enforces_single_admin_and_platform_identity() -> None:
    project_root = Path(__file__).resolve().parents[1]
    schema = (project_root / "migrations" / "v2" / "001_hutao_chat_core_schema.sql").read_text(
        encoding="utf-8"
    )

    assert "PRIMARY KEY (singleton_id)" in schema
    assert "CHECK (singleton_id = 1)" in schema
    assert "UNIQUE KEY uq_admin_profile_profile" in schema
    assert "UNIQUE KEY uq_platform_accounts_identity (platform, platform_user_id, platform_group_id)" in schema
    assert "UNIQUE KEY uq_personas_code (code)" in schema
    assert "UNIQUE KEY uq_persona_versions_label (persona_id, version_label)" in schema
    assert "platform_group_id VARCHAR(128) NOT NULL DEFAULT ''" in schema
    assert "merged_into_profile_id" in schema


def test_database_v2_relationship_permissions_are_strict() -> None:
    admin = permissions_for_relationship("admin_partner")
    normal = permissions_for_relationship("normal_friend")
    blocked = permissions_for_relationship("blocked")

    assert admin.can_view_owner_private is True
    assert admin.can_view_chat_history is True
    assert admin.can_set_relationship is True
    assert admin.can_bind_accounts is True
    assert admin.can_use_voice is True
    assert admin.can_write_long_term_memory is True

    assert normal.can_view_owner_private is False
    assert normal.can_view_chat_history is False
    assert normal.can_set_relationship is False
    assert normal.can_bind_accounts is False
    assert normal.can_use_voice is False
    assert normal.can_write_long_term_memory is False

    assert blocked == normal


def test_database_v2_normalizers_collapse_legacy_roles() -> None:
    assert normalize_relationship_type("owner") == "normal_friend"
    assert normalize_relationship_type("owner_friend") == "normal_friend"
    assert normalize_relationship_type("owner_relative") == "normal_friend"
    assert normalize_relationship_type("stranger") == "normal_friend"
    assert normalize_relationship_type("friend") == "normal_friend"
    assert normalize_relationship_type("admin_partner") == "admin_partner"
    assert normalize_relationship_type("blocked") == "blocked"
    assert normalize_platform_group_id(None) == ""
    assert normalize_platform_group_id(" 123 ") == "123"


def test_database_v2_migration_discovery_and_split() -> None:
    project_root = Path(__file__).resolve().parents[1]
    migrations_dir = project_root / "migrations" / "v2"
    migrations = discover_migrations(migrations_dir)

    assert [migration.version for migration in migrations] == [
        "v2.001_hutao_chat_core_schema",
        "v2.002_knowledge_lifecycle",
        "v2.003_persona_management",
        "v2.004_public_web_auth",
        "v2.005_public_web_password_reset",
        "v2.006_semantic_memory_outbox",
    ]
    assert DATABASE_V2_SCHEMA_VERSION == "v2.001_hutao_chat_core_schema"
    assert "hutao_chat_core" in DATABASE_V2_SCHEMA_DESCRIPTION

    statements = split_sql_statements(migrations[0].path.read_text(encoding="utf-8"))
    assert len(statements) >= 20
    assert statements[0].startswith("CREATE TABLE IF NOT EXISTS schema_migrations")
    assert all(not statement.endswith(";") for statement in statements)


def test_split_sql_statements_keeps_trigger_body_with_custom_delimiter() -> None:
    statements = split_sql_statements(
        """
        CREATE TABLE events (id INT NOT NULL);
        DELIMITER $$
        CREATE TRIGGER events_after_insert
        AFTER INSERT ON events
        FOR EACH ROW
        BEGIN
            INSERT INTO audit_log (event_id) VALUES (NEW.id);
            INSERT INTO work_queue (event_id) VALUES (NEW.id);
        END$$
        DELIMITER ;
        INSERT INTO schema_migrations (version) VALUES ('v2.test');
        """
    )

    assert statements == [
        "CREATE TABLE events (id INT NOT NULL)",
        "CREATE TRIGGER events_after_insert\n        AFTER INSERT ON events\n        FOR EACH ROW\n        BEGIN\n            INSERT INTO audit_log (event_id) VALUES (NEW.id);\n            INSERT INTO work_queue (event_id) VALUES (NEW.id);\n        END",
        "INSERT INTO schema_migrations (version) VALUES ('v2.test')",
    ]


def test_database_v2_migration_runner_records_versions(tmp_path: Path) -> None:
    migration_path = tmp_path / "001_test.sql"
    migration_path.write_text(
        """
        -- test migration
        CREATE TABLE IF NOT EXISTS profiles (id CHAR(36) NOT NULL);
        CREATE TABLE IF NOT EXISTS platform_accounts (id CHAR(36) NOT NULL);
        """,
        encoding="utf-8",
    )
    repository = RecordingV2MigrationRepository()

    applied = asyncio.run(
        apply_pending_migrations(
            repository=repository,  # type: ignore[arg-type]
            migrations_dir=tmp_path,
        )
    )
    applied_again = asyncio.run(
        apply_pending_migrations(
            repository=repository,  # type: ignore[arg-type]
            migrations_dir=tmp_path,
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert applied == ["v2.001_test"]
    assert applied_again == []
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS profiles" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS platform_accounts" in executed_sql
    assert "INSERT INTO schema_migrations" in executed_sql
    assert "v2.001_test" in repository.applied_versions


def test_database_v2_migration_runner_does_not_duplicate_self_recorded_version(
    tmp_path: Path,
) -> None:
    migration_path = tmp_path / "001_self_recording.sql"
    migration_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS profiles (id CHAR(36) NOT NULL);
        INSERT INTO schema_migrations (version, description, applied_at)
        VALUES ('v2.001_self_recording', 'self recorded migration', CURRENT_TIMESTAMP(3))
        ON DUPLICATE KEY UPDATE description = VALUES(description);
        """,
        encoding="utf-8",
    )
    repository = RecordingV2MigrationRepository()

    applied = asyncio.run(
        apply_pending_migrations(
            repository=repository,  # type: ignore[arg-type]
            migrations_dir=tmp_path,
        )
    )

    version_inserts = [
        params
        for sql, params in repository.statements
        if "INSERT INTO schema_migrations" in sql
    ]
    assert applied == ["v2.001_self_recording"]
    assert version_inserts == [()]


def test_database_v2_migration_runner_rejects_non_target_database_name() -> None:
    validate_target_database("hutao_chat_core")
    validate_target_database("isolated_test_db", allow_non_target=True)

    try:
        validate_target_database("xiaohe_core")
    except ValueError as exc:
        assert "MYSQL_DATABASE=hutao_chat_core" in str(exc)
        assert "xiaohe_core" in str(exc)
    else:
        raise AssertionError("V2 migration runner should reject non-target database names")


def test_database_v2_jsonl_migration_dry_run_summarizes_legacy_files(tmp_path: Path) -> None:
    (tmp_path / "contacts.jsonl").write_text(
        "\n".join(
            [
                '{"id":"contact-owner","display_name":"owner","relationship_role":"owner","trust_level":100,"affection_level":100}',
                '{"id":"contact-friend","display_name":"friend","relationship_role":"owner_relative","trust_level":40,"affection_level":40}',
                '{"id":"contact-blocked","display_name":"blocked","relationship_role":"blocked","trust_level":0,"affection_level":0}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "messages.jsonl").write_text(
        '{"id":"message-1","session_id":"session-1","user_id":"qq-123456","role":"user","content":"hi","content_hash":"h","model_invocation_id":null,"created_at":"2026-07-07T01:00:00+00:00"}\n',
        encoding="utf-8",
    )

    snapshot = load_legacy_jsonl_snapshot(tmp_path)
    summary = summarize_snapshot(snapshot)

    assert summary["contacts"] == 3
    assert summary["messages"] == 1
    assert summary["legacy_owner_contacts"] == 1
    assert summary["legacy_normal_contacts"] == 1
    assert summary["legacy_blocked_contacts"] == 1


def test_database_v2_readiness_passes_when_schema_tables_and_admin_are_ready(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_V2_ENABLED", "true")
    settings = load_settings()
    object.__setattr__(settings, "mysql_database", "hutao_chat_core")
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        {"version": DATABASE_V2_SCHEMA_VERSION},
        *[{"TABLE_NAME": table_name} for table_name in REQUIRED_V2_TABLES],
        {"profile_id": "profile-admin"},
    ]

    result = asyncio.run(
        check_database_v2_readiness(
            repository=repository,
            settings=settings,
        )
    )

    assert result.status == "PASS"
    assert all(check.passed for check in result.checks)


def test_database_v2_readiness_fails_when_required_table_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_V2_ENABLED", "true")
    settings = load_settings()
    object.__setattr__(settings, "mysql_database", "hutao_chat_core")
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        {"version": DATABASE_V2_SCHEMA_VERSION},
        None,
        *[{"TABLE_NAME": table_name} for table_name in REQUIRED_V2_TABLES[1:]],
        {"profile_id": "profile-admin"},
    ]

    result = asyncio.run(
        check_database_v2_readiness(
            repository=repository,
            settings=settings,
        )
    )

    assert result.status == "FAIL"
    failed = [check for check in result.checks if not check.passed]
    assert failed[0].name == "table:schema_migrations"


def test_database_v2_readiness_requires_enabled_and_target_database(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_V2_ENABLED", "false")
    settings = load_settings()
    object.__setattr__(settings, "mysql_database", "xiaohe_core")
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        {"version": DATABASE_V2_SCHEMA_VERSION},
        *[{"TABLE_NAME": table_name} for table_name in REQUIRED_V2_TABLES],
        {"profile_id": "profile-admin"},
    ]

    result = asyncio.run(
        check_database_v2_readiness(
            repository=repository,
            settings=settings,
        )
    )

    failed_names = {check.name for check in result.checks if not check.passed}
    assert result.status == "FAIL"
    assert "target_database" in failed_names
    assert "database_v2_enabled" in failed_names


def test_database_v2_readiness_accepts_bootstrap_ids_when_admin_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_V2_ENABLED", "true")
    monkeypatch.setenv("OWNER_BOOTSTRAP_QQ_IDS", "10001")
    settings = load_settings()
    object.__setattr__(settings, "mysql_database", "hutao_chat_core")
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        {"version": DATABASE_V2_SCHEMA_VERSION},
        *[{"TABLE_NAME": table_name} for table_name in REQUIRED_V2_TABLES],
        None,
    ]

    result = asyncio.run(
        check_database_v2_readiness(
            repository=repository,
            settings=settings,
        )
    )

    assert result.status == "PASS"
    assert result.checks[-1].name == "admin_profile"
    assert "bootstrap ids configured" in result.checks[-1].detail


def test_database_v2_smoke_helpers_validate_expected_row_counts() -> None:
    assert smoke_row_counts_pass(
        {
            "conversations": 1,
            "messages": 2,
            "model_invocations": 1,
            "persona_evaluations": 1,
        }
    )
    assert not smoke_row_counts_pass(
        {
            "conversations": 1,
            "messages": 1,
            "model_invocations": 1,
            "persona_evaluations": 1,
        }
    )


def test_database_v2_smoke_selects_first_bootstrap_id(monkeypatch) -> None:
    monkeypatch.setenv("OWNER_BOOTSTRAP_QQ_IDS", "10001,10002")
    monkeypatch.setenv("OWNER_BOOTSTRAP_WECHAT_IDS", "wxid_admin,wxid_alt")
    settings = load_settings()

    assert first_bootstrap_id(settings, platform="qq") == "10001"
    assert first_bootstrap_id(settings, platform="wechat") == "wxid_admin"
    assert first_bootstrap_id(settings, platform="telegram") == ""


def test_database_v2_smoke_counts_rows_from_v2_tables() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        {"id": "conversation-1"},
        {"count": 2},
        {"count": 1},
        {"count": 1},
    ]

    counts = asyncio.run(
        count_database_v2_smoke_rows(
            repository=repository,
            platform="qq",
            session_token="database-v2-smoke-qq-10001-test",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert counts == {
        "conversations": 1,
        "messages": 2,
        "model_invocations": 1,
        "persona_evaluations": 1,
    }
    assert "FROM conversations" in executed_sql
    assert "FROM messages" in executed_sql
    assert "FROM model_invocations" in executed_sql
    assert "FROM persona_evaluations" in executed_sql


def test_database_v2_bootstrap_id_parser() -> None:
    assert parse_bootstrap_ids(" 123,456；789  123;wxid ") == [
        "123",
        "456",
        "789",
        "wxid",
    ]
    assert parse_bootstrap_ids("") == []


def test_database_v2_settings_load_bootstrap_fields(monkeypatch) -> None:
    monkeypatch.setenv("OWNER_BOOTSTRAP_QQ_IDS", "10001,10002")
    monkeypatch.setenv("OWNER_BOOTSTRAP_WECHAT_IDS", "wxid_admin")
    monkeypatch.setenv("DATABASE_V2_ENABLED", "true")

    settings = load_settings()

    assert settings.owner_bootstrap_qq_ids == "10001,10002"
    assert settings.owner_bootstrap_wechat_ids == "wxid_admin"
    assert settings.database_v2_enabled is True


def test_database_v2_runtime_gate_requires_enabled_supported_platform_and_user(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_V2_ENABLED", "true")
    settings = load_settings()

    assert should_use_database_v2(settings, platform="qq", platform_user_id="10001") is True
    assert should_use_database_v2(settings, platform="wechat", platform_user_id="wxid") is True
    assert should_use_database_v2(settings, platform="telegram", platform_user_id="10001") is False
    assert should_use_database_v2(settings, platform="qq", platform_user_id="") is False
    assert should_use_database_v2(
        settings,
        platform=None,
        platform_user_id=None,
        trusted_core_profile=True,
    ) is True

    monkeypatch.setenv("DATABASE_V2_ENABLED", "false")
    assert should_use_database_v2(load_settings(), platform="qq", platform_user_id="10001") is False
    assert should_use_database_v2(
        load_settings(),
        platform=None,
        platform_user_id=None,
        trusted_core_profile=True,
    ) is False


def test_database_v2_mysql_repository_binds_core_chat_to_active_profile() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [None, {"id": "profile-web"}, {"id": "profile-web"}]

    session = asyncio.run(
        repository.ensure_session(
            user_id="profile-web",
            client_session_id="server-session",
        )
    )
    memory = asyncio.run(
        repository.save_memory(
            user_id="profile-web",
            session_id=None,
            memory_type="conversation_preference",
            content="回复用短句",
            confidence=0.9,
        )
    )

    conversation_insert = next(
        params
        for sql, params in repository.statements
        if "INSERT INTO conversations" in sql
    )
    memory_insert = next(
        params
        for sql, params in repository.statements
        if "INSERT INTO memories" in sql
    )
    profile_queries = [sql for sql, _params in repository.statements if "FROM profiles" in sql]

    assert session.user_id == "profile-web"
    assert conversation_insert[1] == "core"
    assert conversation_insert[4] == "profile-web"
    assert memory.user_id == "profile-web"
    assert memory_insert[1] == "profile-web"
    assert len(profile_queries) == 2


def test_database_v2_relationship_service_bootstraps_from_settings(monkeypatch) -> None:
    monkeypatch.setenv("OWNER_BOOTSTRAP_QQ_IDS", "10001, 10001, 10002")
    monkeypatch.setenv("OWNER_BOOTSTRAP_WECHAT_IDS", "wxid_admin")
    monkeypatch.setenv("HUTAO_OWNER_NAME", "admin")
    repository = FakeDatabaseV2Repository()
    service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]

    profile_id = asyncio.run(service.bootstrap_admin_from_settings(load_settings()))

    assert profile_id == "profile-admin"
    assert repository.bootstrap_args == {
        "qq_ids": ["10001", "10002"],
        "wechat_ids": ["wxid_admin"],
        "display_name": "admin",
    }


def test_database_v2_relationship_service_allows_normal_friend() -> None:
    repository = FakeDatabaseV2Repository("normal_friend")
    service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]

    resolution = asyncio.run(
        service.resolve(
            PlatformIdentity(
                platform="qq",
                platform_user_id="20002",
                display_name="普通朋友",
            )
        )
    )

    assert resolution.should_enter_chat_service is True
    assert resolution.should_reply is True
    assert resolution.fixed_reply is None
    assert resolution.reason_code == "allowed"
    assert resolution.to_model_context()["relationship_type"] == "normal_friend"
    assert resolution.to_model_context()["effective_relationship_type"] == "normal_friend"
    assert repository.resolve_args == {
        "platform": "qq",
        "platform_user_id": "20002",
        "platform_group_id": None,
        "display_name": "普通朋友",
    }


def test_database_v2_relationship_service_blocks_private_and_group() -> None:
    private_service = DatabaseV2RelationshipService(  # type: ignore[arg-type]
        FakeDatabaseV2Repository("normal_friend", account_status="blocked")
    )
    private_resolution = asyncio.run(
        private_service.resolve(
            PlatformIdentity(
                platform="qq",
                platform_user_id="30003",
                conversation_type="private",
            )
        )
    )
    assert private_resolution.should_enter_chat_service is False
    assert private_resolution.should_reply is True
    assert private_resolution.fixed_reply == "现在不方便继续聊。"
    assert private_resolution.to_model_context()["effective_relationship_type"] == "blocked"

    group_service = DatabaseV2RelationshipService(  # type: ignore[arg-type]
        FakeDatabaseV2Repository("blocked")
    )
    group_resolution = asyncio.run(
        group_service.resolve(
            PlatformIdentity(
                platform="qq",
                platform_user_id="30003",
                platform_group_id="group-1",
                conversation_type="group",
            )
        )
    )
    assert group_resolution.should_enter_chat_service is False
    assert group_resolution.should_reply is False
    assert group_resolution.fixed_reply == "现在不方便继续聊。"


def test_database_v2_relationship_service_admin_model_context() -> None:
    service = DatabaseV2RelationshipService(  # type: ignore[arg-type]
        FakeDatabaseV2Repository("admin_partner")
    )

    resolution = asyncio.run(
        service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )
    model_context = resolution.to_model_context()

    assert model_context["relationship_type"] == "admin_partner"
    assert model_context["effective_relationship_type"] == "admin_partner"
    assert model_context["verified"] is True
    permissions = model_context["permissions"]
    assert isinstance(permissions, dict)
    assert permissions["can_view_chat_history"] is True
    assert permissions["can_set_relationship"] is True


def test_database_v2_admin_command_parser_accepts_supported_commands() -> None:
    set_relationship = parse_v2_admin_command("设置关系 qq 123456 normal_friend 张三")
    assert not isinstance(set_relationship, str)
    assert set_relationship is not None
    assert set_relationship.name == "set_relationship"
    assert set_relationship.args == {
        "platform": "qq",
        "platform_user_id": "123456",
        "relationship_type": "normal_friend",
        "display_name": "张三",
    }

    bind_accounts = parse_v2_admin_command("绑定账号 qq 123456 wechat wxid_abc")
    assert not isinstance(bind_accounts, str)
    assert bind_accounts is not None
    assert bind_accounts.name == "bind_accounts"
    assert bind_accounts.args["source_platform"] == "qq"
    assert bind_accounts.args["target_platform"] == "wechat"

    assert parse_v2_admin_command("最近聊天").name == "recent_chats"  # type: ignore[union-attr]
    assert parse_v2_admin_command("待确认关系").name == "pending_claims"  # type: ignore[union-attr]
    assert parse_v2_admin_command("确认关系 claim-1").name == "approve_claim"  # type: ignore[union-attr]
    assert parse_v2_admin_command("拒绝关系 claim-1").name == "reject_claim"  # type: ignore[union-attr]


def test_database_v2_admin_command_parser_rejects_invalid_targets() -> None:
    assert parse_v2_admin_command("普通聊天") is None
    assert parse_v2_admin_command("设置关系 qq 123456 owner_friend") == "unsupported relationship_type"
    assert parse_v2_admin_command("设置关系 telegram 123 normal_friend") == "unsupported platform"
    assert parse_v2_admin_command("绑定账号 qq 123") == (
        "绑定账号 requires: 绑定账号 <platform> <platform_user_id> <platform> <platform_user_id>"
    )


def test_database_v2_admin_command_policy_requires_admin_partner() -> None:
    normal_service = DatabaseV2RelationshipService(  # type: ignore[arg-type]
        FakeDatabaseV2Repository("normal_friend")
    )
    normal_resolution = asyncio.run(
        normal_service.resolve(PlatformIdentity(platform="qq", platform_user_id="20002"))
    )

    denied = decide_v2_admin_command(
        command_text="拉黑 qq 123456",
        resolution=normal_resolution,
    )

    assert denied.is_command is True
    assert denied.authorized is False
    assert denied.reason_code == "admin_required"
    assert denied.command is not None
    assert denied.command.name == "block"


def test_database_v2_admin_command_policy_authorizes_admin_partner() -> None:
    admin_service = DatabaseV2RelationshipService(  # type: ignore[arg-type]
        FakeDatabaseV2Repository("admin_partner")
    )
    admin_resolution = asyncio.run(
        admin_service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )

    decision = decide_v2_admin_command(
        command_text="查看聊天 qq 123456",
        resolution=admin_resolution,
    )

    assert decision.is_command is True
    assert decision.authorized is True
    assert decision.reason_code == "authorized"
    assert decision.command is not None
    assert decision.command.name == "view_chat"
    assert decision.command.args == {
        "platform": "qq",
        "platform_user_id": "123456",
    }


def test_database_v2_admin_command_policy_handles_invalid_and_non_commands() -> None:
    admin_service = DatabaseV2RelationshipService(  # type: ignore[arg-type]
        FakeDatabaseV2Repository("admin_partner")
    )
    admin_resolution = asyncio.run(
        admin_service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )

    not_command = decide_v2_admin_command(
        command_text="今天吃什么",
        resolution=admin_resolution,
    )
    invalid = decide_v2_admin_command(
        command_text="拉黑 qq",
        resolution=admin_resolution,
    )

    assert not_command.is_command is False
    assert not_command.reason_code == "not_command"
    assert invalid.is_command is True
    assert invalid.authorized is False
    assert invalid.reason_code == "invalid_command"


def test_database_v2_command_executor_sets_relationship() -> None:
    repository = ExecutingFakeDatabaseV2Repository()
    service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    resolution = asyncio.run(
        service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )
    decision = decide_v2_admin_command(
        command_text="设置关系 qq 123456 blocked 张三",
        resolution=resolution,
    )

    result = asyncio.run(
        execute_v2_admin_command(
            decision=decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id=resolution.context.profile.id,
        )
    )

    assert result.executed is True
    assert result.status == "relationship_updated"
    assert result.data["relationship_type"] == "blocked"
    assert repository.set_relationship_calls[-1]["platform"] == "qq"
    assert repository.set_relationship_calls[-1]["platform_user_id"] == "123456"
    assert repository.set_relationship_calls[-1]["relationship_type"] == "blocked"
    assert repository.set_relationship_calls[-1]["changed_by_profile_id"] == "profile-1"


def test_database_v2_command_executor_blocks_and_unblocks() -> None:
    repository = ExecutingFakeDatabaseV2Repository()
    service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    resolution = asyncio.run(
        service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )

    block_decision = decide_v2_admin_command(
        command_text="拉黑 qq 123456",
        resolution=resolution,
    )
    unblock_decision = decide_v2_admin_command(
        command_text="解除拉黑 qq 123456",
        resolution=resolution,
    )
    block_result = asyncio.run(
        execute_v2_admin_command(
            decision=block_decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )
    unblock_result = asyncio.run(
        execute_v2_admin_command(
            decision=unblock_decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )

    assert block_result.status == "blocked"
    assert unblock_result.status == "unblocked"
    assert repository.set_relationship_calls[0]["relationship_type"] == "blocked"
    assert repository.set_relationship_calls[1]["relationship_type"] == "normal_friend"


def test_database_v2_command_executor_binds_accounts() -> None:
    repository = ExecutingFakeDatabaseV2Repository()
    service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    resolution = asyncio.run(
        service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )
    decision = decide_v2_admin_command(
        command_text="绑定账号 qq 123456 wechat wxid_abc",
        resolution=resolution,
    )

    result = asyncio.run(
        execute_v2_admin_command(
            decision=decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )

    assert result.executed is True
    assert result.status == "accounts_bound"
    assert result.data["profile_id"] == "profile-bound"
    assert repository.bind_accounts_calls == [
        {
            "source_platform": "qq",
            "source_platform_user_id": "123456",
            "target_platform": "wechat",
            "target_platform_user_id": "wxid_abc",
            "changed_by_profile_id": "profile-admin",
            "reason": "admin command bind_accounts",
        }
    ]


def test_database_v2_command_executor_refuses_unauthorized_and_executes_admin_queries() -> None:
    normal_repository = ExecutingFakeDatabaseV2Repository("normal_friend")
    normal_service = DatabaseV2RelationshipService(normal_repository)  # type: ignore[arg-type]
    normal_resolution = asyncio.run(
        normal_service.resolve(PlatformIdentity(platform="qq", platform_user_id="20002"))
    )
    denied_decision = decide_v2_admin_command(
        command_text="拉黑 qq 123456",
        resolution=normal_resolution,
    )
    denied_result = asyncio.run(
        execute_v2_admin_command(
            decision=denied_decision,
            repository=normal_repository,  # type: ignore[arg-type]
            actor_profile_id="profile-normal",
        )
    )

    admin_repository = ExecutingFakeDatabaseV2Repository("admin_partner")
    admin_service = DatabaseV2RelationshipService(admin_repository)  # type: ignore[arg-type]
    admin_resolution = asyncio.run(
        admin_service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )
    pending_decision = decide_v2_admin_command(
        command_text="待确认关系",
        resolution=admin_resolution,
    )
    pending_result = asyncio.run(
        execute_v2_admin_command(
            decision=pending_decision,
            repository=admin_repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )

    assert denied_result.executed is False
    assert denied_result.status == "admin_required"
    assert normal_repository.set_relationship_calls == []
    assert pending_result.executed is True
    assert pending_result.status == "pending_claims_loaded"
    assert pending_result.data["claims"] == [
        {
            "id": "claim-1",
            "platform": "qq",
            "platform_user_id": "123456",
            "claimed_name": "张三",
            "claimed_relation_text": "我是你的同学",
            "status": "pending",
            "reviewed_by_profile_id": None,
            "created_at": "2026-07-06 20:00:00.000",
            "reviewed_at": None,
        }
    ]


def test_database_v2_command_executor_loads_recent_and_chat_history() -> None:
    repository = ExecutingFakeDatabaseV2Repository("admin_partner")
    service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    resolution = asyncio.run(
        service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )

    recent_decision = decide_v2_admin_command(
        command_text="最近聊天",
        resolution=resolution,
    )
    chat_decision = decide_v2_admin_command(
        command_text="查看聊天 qq 123456",
        resolution=resolution,
    )
    recent_result = asyncio.run(
        execute_v2_admin_command(
            decision=recent_decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )
    chat_result = asyncio.run(
        execute_v2_admin_command(
            decision=chat_decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )

    assert recent_result.status == "recent_chats_loaded"
    assert recent_result.data["chats"][0]["conversation_id"] == "conversation-1"  # type: ignore[index]
    assert chat_result.status == "chat_history_loaded"
    assert chat_result.data["messages"][0]["content"] == "你好"  # type: ignore[index]
    assert repository.chat_history_calls == [
        {"platform": "qq", "platform_user_id": "123456", "limit": 30}
    ]


def test_database_v2_command_executor_approves_and_rejects_claims() -> None:
    repository = ExecutingFakeDatabaseV2Repository("admin_partner")
    service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    resolution = asyncio.run(
        service.resolve(PlatformIdentity(platform="qq", platform_user_id="10001"))
    )

    approve_decision = decide_v2_admin_command(
        command_text="确认关系 claim-1",
        resolution=resolution,
    )
    reject_decision = decide_v2_admin_command(
        command_text="拒绝关系 claim-2",
        resolution=resolution,
    )
    approve_result = asyncio.run(
        execute_v2_admin_command(
            decision=approve_decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )
    reject_result = asyncio.run(
        execute_v2_admin_command(
            decision=reject_decision,
            repository=repository,  # type: ignore[arg-type]
            actor_profile_id="profile-admin",
        )
    )

    assert approve_result.status == "approved"
    assert approve_result.data["relationship_type"] == "normal_friend"
    assert reject_result.status == "rejected"
    assert repository.approve_claim_calls == [
        {"claim_id": "claim-1", "reviewed_by_profile_id": "profile-admin"}
    ]
    assert repository.reject_claim_calls == [
        {"claim_id": "claim-2", "reviewed_by_profile_id": "profile-admin"}
    ]


def test_database_v2_platform_command_service_normalizes_prefixes() -> None:
    assert normalize_platform_command_text("胡桃 最近聊天") == "最近聊天"
    assert normalize_platform_command_text("小何：查看关系 qq 123456") == "小何：查看关系 qq 123456"
    assert normalize_platform_command_text("今天吃什么") == "今天吃什么"


def test_database_v2_platform_command_service_passes_non_command_to_chat() -> None:
    repository = ExecutingFakeDatabaseV2Repository("normal_friend")
    relationship_service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    command_service = DatabaseV2PlatformCommandService(
        relationship_service=relationship_service,
        repository=repository,  # type: ignore[arg-type]
    )

    result = asyncio.run(
        command_service.handle_message(
            identity=PlatformIdentity(platform="qq", platform_user_id="20002"),
            message_text="今天吃什么",
            message_id="message-1",
        )
    )

    assert result.is_command is False
    assert result.should_enter_chat_service is True
    assert result.should_reply is True
    assert result.reply_text is None
    assert repository.command_events == []


def test_database_v2_platform_command_service_executes_admin_command_and_audits() -> None:
    repository = ExecutingFakeDatabaseV2Repository("admin_partner")
    relationship_service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    command_service = DatabaseV2PlatformCommandService(
        relationship_service=relationship_service,
        repository=repository,  # type: ignore[arg-type]
    )

    result = asyncio.run(
        command_service.handle_message(
            identity=PlatformIdentity(platform="qq", platform_user_id="10001"),
            message_text="胡桃 拉黑 qq 123456",
            message_id="message-admin-command",
        )
    )

    assert result.is_command is True
    assert result.should_enter_chat_service is False
    assert result.execution_result is not None
    assert result.execution_result.status == "blocked"
    assert repository.set_relationship_calls[-1]["relationship_type"] == "blocked"
    assert repository.command_events == [
        {
            "message_id": "message-admin-command",
            "actor_profile_id": "profile-1",
            "command_name": "block",
            "platform": "qq",
            "target_platform_user_id": "123456",
            "status": "accepted",
            "reason_code": "blocked",
            "details": {
                "profile_id": "profile-1",
                "platform_account_id": "account-1",
                "relationship_type": "blocked",
                "effective_relationship_type": "blocked",
                "verified": True,
            },
        }
    ]


def test_database_v2_platform_command_service_rejects_non_admin_command_and_audits() -> None:
    repository = ExecutingFakeDatabaseV2Repository("normal_friend")
    relationship_service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    command_service = DatabaseV2PlatformCommandService(
        relationship_service=relationship_service,
        repository=repository,  # type: ignore[arg-type]
    )

    result = asyncio.run(
        command_service.handle_message(
            identity=PlatformIdentity(platform="qq", platform_user_id="20002"),
            message_text="胡桃 拉黑 qq 123456",
            message_id="message-normal-command",
        )
    )

    assert result.is_command is True
    assert result.should_enter_chat_service is False
    assert result.execution_result is None
    assert result.reason_code == "admin_required"
    assert result.reply_text == "没有权限使用这个命令。"
    assert repository.set_relationship_calls == []
    assert repository.command_events[-1]["status"] == "rejected"
    assert repository.command_events[-1]["reason_code"] == "admin_required"
    assert repository.command_events[-1]["command_name"] == "block"


def test_database_v2_platform_command_service_blocks_before_command_pipeline() -> None:
    repository = ExecutingFakeDatabaseV2Repository("blocked")
    relationship_service = DatabaseV2RelationshipService(repository)  # type: ignore[arg-type]
    command_service = DatabaseV2PlatformCommandService(
        relationship_service=relationship_service,
        repository=repository,  # type: ignore[arg-type]
    )

    result = asyncio.run(
        command_service.handle_message(
            identity=PlatformIdentity(platform="qq", platform_user_id="30003"),
            message_text="小何 最近聊天",
            message_id="message-blocked",
        )
    )

    assert result.is_command is False
    assert result.should_enter_chat_service is False
    assert result.reason_code == "blocked_profile_or_account"
    assert repository.command_events == []


def test_database_v2_mysql_repository_bootstraps_single_admin() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [None]

    profile_id = asyncio.run(
        repository.bootstrap_admin_if_missing(
            qq_ids=["3471764547", "3471764547", ""],
            wechat_ids=["wxid_admin"],
            display_name="管理员",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert profile_id is not None
    assert "FROM admin_profile" in executed_sql
    assert "INSERT INTO profiles" in executed_sql
    assert "INSERT INTO admin_profile" in executed_sql
    assert executed_sql.count("INSERT INTO platform_accounts") == 2
    assert "INSERT INTO relationship_events" in executed_sql
    assert "admin_partner" in executed_sql


def test_database_v2_mysql_repository_resolves_unknown_as_normal_friend() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        None,
        profile_account_row(profile_id="profile-new", account_id="account-new"),
    ]
    repository.fetchall_results = [[]]

    context = asyncio.run(
        repository.resolve_relationship_context(
            platform="qq",
            platform_user_id="20002",
            display_name="新朋友",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert context.profile.relationship_type == "normal_friend"
    assert context.profile.verified is False
    assert context.effective_relationship_type == "normal_friend"
    assert context.permissions.can_view_chat_history is False
    assert "INSERT INTO profiles" in executed_sql
    assert "INSERT INTO platform_accounts" in executed_sql
    assert "INSERT INTO relationship_events" in executed_sql


def test_database_v2_mysql_repository_ensures_default_personas() -> None:
    repository = RecordingMySQLDatabaseV2Repository()

    asyncio.run(repository.ensure_default_personas())

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    params_text = str(repository.statements)
    assert executed_sql.count("INSERT INTO personas") == 1
    assert executed_sql.count("INSERT INTO persona_versions") == 1
    assert "ON DUPLICATE KEY UPDATE" in executed_sql
    assert "hutao_v1" in params_text
    assert "xiaohe" not in params_text


def test_database_v2_mysql_repository_resolves_normal_friend_default_persona() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    relationship = FakeDatabaseV2Repository("normal_friend").context
    repository.fetchone_results = [
        None,
        persona_row(code="hutao_v1", display_name="胡桃"),
    ]

    persona = asyncio.run(
        repository.resolve_persona_context(relationship_context=relationship)
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert persona.persona.code == "hutao_v1"
    assert persona.source_scope == "relationship_type"
    assert persona.version is not None
    assert persona.version.style_rules_json == {"reply_length": "short"}
    assert "FROM persona_runtime_bindings" in executed_sql
    assert "FROM personas p" in executed_sql


def test_database_v2_mysql_repository_resolves_admin_to_same_default_persona() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    relationship = FakeDatabaseV2Repository("admin_partner").context
    repository.fetchone_results = [
        None,
        persona_row(code="hutao_v1", display_name="胡桃"),
    ]

    persona = asyncio.run(
        repository.resolve_persona_context(relationship_context=relationship)
    )

    assert persona.persona.code == "hutao_v1"
    assert persona.persona.default_for_admin is True
    assert persona.source_scope == "relationship_type"


def test_database_v2_mysql_repository_conversation_persona_overrides_defaults() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    relationship = FakeDatabaseV2Repository("normal_friend").context
    repository.fetchone_results = [
        persona_row(code="hutao_v1", display_name="胡桃", state_json='{"tone":"quiet"}'),
    ]

    persona = asyncio.run(
        repository.resolve_persona_context(
            relationship_context=relationship,
            conversation_id="conversation-1",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert persona.persona.code == "hutao_v1"
    assert persona.source_scope == "conversation"
    assert persona.state_json == {"tone": "quiet"}
    assert "FROM conversation_persona_state" in executed_sql
    assert "FROM persona_runtime_bindings" not in executed_sql


def test_database_v2_mysql_repository_falls_back_when_personas_are_missing() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    relationship = FakeDatabaseV2Repository("admin_partner").context
    repository.fetchone_results = [
        None,
        None,
    ]

    persona = asyncio.run(
        repository.resolve_persona_context(relationship_context=relationship)
    )

    assert persona.persona.code == "hutao_v1"
    assert persona.source_scope == "fallback"
    assert persona.version is None


def test_database_v2_mysql_repository_supports_chat_service_core_writes() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        None,
        profile_account_row(profile_id="profile-friend", account_id="account-friend"),
        conversation_row(conversation_id="conversation-1"),
        conversation_row(conversation_id="conversation-1"),
        {"id": "account-friend"},
        conversation_row(conversation_id="conversation-1"),
    ]
    repository.fetchall_results = [[]]

    session = asyncio.run(
        repository.ensure_session(
            user_id="qq-123456",
            client_session_id="qq-private-123456",
        )
    )
    invocation = asyncio.run(
        repository.save_model_invocation(
            session_id="conversation-1",
            user_id="qq-123456",
            provider="deepseek",
            model="deepseek-v4-pro",
            used_live_api=True,
            fallback_used=False,
            latency_ms=12.3,
            prompt_hash="p" * 64,
            response_hash="r" * 64,
            error=None,
            request_metadata_json={"api_path": "/api/v1/chat"},
        )
    )
    message = asyncio.run(
        repository.save_message(
            session_id="conversation-1",
            user_id="qq-123456",
            role="assistant",
            content="reply",
            model_invocation_id=invocation.id,
        )
    )
    memory = asyncio.run(
        repository.save_memory(
            user_id="qq-123456",
            session_id="conversation-1",
            memory_type="conversation_preference",
            content="短句",
            source_message_id=message.id,
            confidence=0.8,
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert session.id
    assert invocation.session_id == "conversation-1"
    assert message.session_id == "conversation-1"
    assert memory.user_id == "qq-123456"
    assert "INSERT INTO conversations" in executed_sql
    assert "INSERT INTO model_invocations" in executed_sql
    assert "INSERT INTO messages" in executed_sql
    assert "INSERT INTO memories" in executed_sql
    assert "INSERT INTO sessions" not in executed_sql


def test_database_v2_mysql_repository_maps_v2_profile_to_legacy_relationship_context() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        profile_account_row(
            profile_id="profile-admin",
            account_id="account-admin",
            relationship_type="admin_partner",
            verified=True,
        )
    ]
    repository.fetchall_results = [[]]

    contact = asyncio.run(
        repository.resolve_contact(
            platform="qq",
            platform_user_id="10001",
        )
    )

    assert contact.id == "profile-admin"
    assert contact.relationship_role == "owner"
    assert contact.authority_level == 100


def test_database_v2_mysql_repository_account_block_overrides_profile_permissions() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        profile_account_row(
            profile_id="profile-normal",
            account_id="account-blocked",
            relationship_type="normal_friend",
            account_status="blocked",
        )
    ]
    repository.fetchall_results = [[{"label_type": "friend", "label_text": "管理员朋友"}]]

    context = asyncio.run(
        repository.resolve_relationship_context(
            platform="qq",
            platform_user_id="30003",
        )
    )

    assert context.profile.relationship_type == "normal_friend"
    assert context.platform_account.status == "blocked"
    assert context.effective_relationship_type == "blocked"
    assert context.permissions.can_view_chat_history is False
    assert context.social_labels == ("friend:管理员朋友",)


def test_database_v2_mysql_repository_sets_relationship() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        profile_account_row(profile_id="profile-1", account_id="account-1"),
        profile_account_row(
            profile_id="profile-1",
            account_id="account-1",
            relationship_type="admin_partner",
            verified=True,
        ),
    ]
    repository.fetchall_results = [[], []]

    context = asyncio.run(
        repository.set_relationship(
            platform="qq",
            platform_user_id="40004",
            relationship_type="admin_partner",
            display_name="管理员",
            changed_by_profile_id="profile-admin",
            reason="owner approved",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert context.profile.relationship_type == "admin_partner"
    assert context.permissions.can_set_relationship is True
    assert "UPDATE profiles" in executed_sql
    assert "INSERT INTO relationship_events" in executed_sql
    assert "set_role" in str(repository.statements)


def test_database_v2_mysql_repository_binds_accounts_by_merging_profiles() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        profile_account_row(profile_id="profile-source", account_id="account-source"),
        profile_account_row(
            profile_id="profile-target",
            account_id="account-target",
            platform="wechat",
            platform_user_id="wxid_target",
        ),
    ]
    repository.fetchall_results = [[], []]

    profile_id = asyncio.run(
        repository.bind_accounts(
            source_platform="qq",
            source_platform_user_id="50005",
            target_platform="wechat",
            target_platform_user_id="wxid_target",
            changed_by_profile_id="profile-admin",
            reason="same person",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert profile_id == "profile-source"
    assert "UPDATE platform_accounts" in executed_sql
    assert "UPDATE model_invocations" in executed_sql
    assert "UPDATE messages" in executed_sql
    assert "UPDATE safety_guard_events" in executed_sql
    assert "UPDATE memories" in executed_sql
    assert "UPDATE relationship_events" in executed_sql
    assert "UPDATE conversations" in executed_sql
    assert "UPDATE platform_command_events" in executed_sql
    assert "UPDATE profiles" in executed_sql
    assert "status = 'merged'" in executed_sql
    assert "DELETE FROM profile_portraits" in executed_sql
    assert "DELETE FROM profile_emotional_state" in executed_sql
    assert "merge" in str(repository.statements)


def test_database_v2_mysql_repository_lists_recent_chats_and_history() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchall_results = [
        [
            {
                "conversation_id": "conversation-1",
                "platform": "qq",
                "conversation_type": "private",
                "platform_thread_id": "123456",
                "title": "张三",
                "owner_profile_id": "profile-friend",
                "owner_display_name": "张三",
                "owner_relationship_type": "normal_friend",
                "last_message_at": "2026-07-06 20:00:00.000",
                "message_count": 2,
            }
        ],
        [
            {
                "id": "message-1",
                "conversation_id": "conversation-1",
                "profile_id": "profile-friend",
                "platform_account_id": "account-friend",
                "platform": "qq",
                "platform_message_id": "msg-1",
                "direction": "inbound",
                "role": "user",
                "content_type": "text",
                "content": "你好",
                "safety_status": "passed",
                "memory_eligible": False,
                "visible_to_admin": True,
                "created_at": "2026-07-06 20:00:00.000",
                "conversation_title": "张三",
            }
        ],
    ]
    repository.fetchone_results = [
        profile_account_row(profile_id="profile-friend", account_id="account-friend")
    ]

    recent = asyncio.run(repository.list_recent_chats(limit=10))
    history = asyncio.run(
        repository.list_chat_history(platform="qq", platform_user_id="123456", limit=30)
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert recent[0].conversation_id == "conversation-1"
    assert recent[0].message_count == 2
    assert history[0].content == "你好"
    assert history[0].visible_to_admin is True
    assert "FROM conversations c" in executed_sql
    assert "LEFT JOIN messages m" in executed_sql
    assert "FROM messages m" in executed_sql
    assert "m.visible_to_admin = TRUE" in executed_sql


def test_database_v2_mysql_repository_lists_pending_claims() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchall_results = [
        [
            {
                "id": "claim-1",
                "platform": "qq",
                "platform_user_id": "123456",
                "claimed_name": "张三",
                "claimed_relation_text": "我是你的同学",
                "status": "pending",
                "reviewed_by_profile_id": None,
                "created_at": "2026-07-06 20:00:00.000",
                "reviewed_at": None,
            }
        ]
    ]

    claims = asyncio.run(repository.list_pending_relationship_claims(limit=20))

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert claims[0].id == "claim-1"
    assert claims[0].claimed_relation_text == "我是你的同学"
    assert "FROM relationship_pending_claims" in executed_sql
    assert "WHERE status = 'pending'" in executed_sql


def test_database_v2_mysql_repository_approves_relationship_claim_without_role_upgrade() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        {
            "id": "claim-1",
            "platform": "qq",
            "platform_user_id": "123456",
            "claimed_name": "张三",
            "claimed_relation_text": "我是你的同学",
            "status": "pending",
            "reviewed_by_profile_id": None,
            "created_at": "2026-07-06 20:00:00.000",
            "reviewed_at": None,
        },
        profile_account_row(profile_id="profile-friend", account_id="account-friend"),
    ]
    repository.fetchall_results = [[]]

    result = asyncio.run(
        repository.approve_relationship_claim(
            claim_id="claim-1",
            reviewed_by_profile_id="profile-admin",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert result["status"] == "approved"
    assert result["relationship_type"] == "normal_friend"
    assert "UPDATE profiles" in executed_sql
    assert "verified = TRUE" in executed_sql
    assert "UPDATE platform_accounts" in executed_sql
    assert "INSERT INTO profile_social_labels" in executed_sql
    assert "UPDATE relationship_pending_claims" in executed_sql
    assert "status = 'approved'" in executed_sql
    assert "INSERT INTO relationship_events" in executed_sql
    assert "admin_partner" not in str(result)


def test_database_v2_mysql_repository_rejects_relationship_claim() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    repository.fetchone_results = [
        {
            "id": "claim-2",
            "platform": "wechat",
            "platform_user_id": "wxid_abc",
            "claimed_name": "李四",
            "claimed_relation_text": "我是你的亲戚",
            "status": "pending",
            "reviewed_by_profile_id": None,
            "created_at": "2026-07-06 20:00:00.000",
            "reviewed_at": None,
        },
        profile_account_row(
            profile_id="profile-friend",
            account_id="account-friend",
            platform="wechat",
            platform_user_id="wxid_abc",
        ),
    ]

    result = asyncio.run(
        repository.reject_relationship_claim(
            claim_id="claim-2",
            reviewed_by_profile_id="profile-admin",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert result == {"status": "rejected", "claim_id": "claim-2"}
    assert "UPDATE relationship_pending_claims" in executed_sql
    assert "status = 'rejected'" in executed_sql
    assert "INSERT INTO relationship_events" in executed_sql
    assert "unverify" in str(repository.statements)


def test_database_v2_mysql_repository_records_platform_command_event() -> None:
    repository = RecordingMySQLDatabaseV2Repository()

    asyncio.run(
        repository.record_platform_command_event(
            message_id="message-1",
            actor_profile_id="profile-admin",
            command_name="block",
            platform="qq",
            target_platform_user_id="123456",
            status="accepted",
            reason_code="blocked",
            details={"status": "blocked", "secret": "sk-123456789012345678901234"},
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    params = repository.statements[-1][1]
    assert "INSERT INTO platform_command_events" in executed_sql
    assert params[1] == "message-1"
    assert params[2] == "profile-admin"
    assert params[3] == "block"
    assert params[4] == "qq"
    assert params[5] == "123456"
    assert params[6] == "accepted"
    assert params[7] == "blocked"
    assert "<REDACTED_API_KEY>" in str(params[8])


def test_database_v2_jsonl_migration_imports_snapshot_into_v2_tables() -> None:
    repository = RecordingMySQLDatabaseV2Repository()
    snapshot = {
        "contacts": [
            {
                "id": "contact-owner",
                "display_name": "owner",
                "relationship_role": "owner",
                "trust_level": 100,
                "affection_level": 100,
                "created_at": "2026-07-07T01:00:00+00:00",
                "updated_at": "2026-07-07T01:00:00+00:00",
            }
        ],
        "platform_identities": [
            {
                "id": "identity-owner",
                "contact_id": "contact-owner",
                "platform": "qq",
                "platform_user_id": "123456",
                "platform_group_id": None,
                "created_at": "2026-07-07T01:00:00+00:00",
                "updated_at": "2026-07-07T01:00:00+00:00",
            }
        ],
        "sessions": [
            {
                "id": "session-1",
                "user_id": "qq-123456",
                "client_session_id": "qq-private-123456",
                "created_at": "2026-07-07T01:00:00+00:00",
                "updated_at": "2026-07-07T01:00:00+00:00",
            }
        ],
        "model_invocations": [
            {
                "id": "invocation-1",
                "session_id": "session-1",
                "user_id": "qq-123456",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "used_live_api": True,
                "fallback_used": False,
                "latency_ms": 1.0,
                "prompt_hash": "p" * 64,
                "response_hash": "r" * 64,
                "error": None,
                "request_metadata_json": {"api_path": "/api/v1/chat"},
                "created_at": "2026-07-07T01:00:00+00:00",
            }
        ],
        "messages": [
            {
                "id": "message-1",
                "session_id": "session-1",
                "user_id": "qq-123456",
                "role": "user",
                "content": "hi",
                "content_hash": "h",
                "model_invocation_id": None,
                "created_at": "2026-07-07T01:00:00+00:00",
            }
        ],
        "persona_evaluations": [
            {
                "id": "evaluation-1",
                "message_id": "message-1",
                "model_invocation_id": "invocation-1",
                "passed": True,
                "score": 1.0,
                "evaluator_provider": "local",
                "evaluator_model": "rules",
                "reasons_json": {"reasons": []},
                "created_at": "2026-07-07T01:00:00+00:00",
            }
        ],
        "memories": [
            {
                "id": "memory-1",
                "user_id": "qq-123456",
                "session_id": "session-1",
                "memory_type": "conversation_preference",
                "content": "短句",
                "content_hash": "m",
                "source_message_id": "message-1",
                "confidence": 0.9,
                "created_at": "2026-07-07T01:00:00+00:00",
                "updated_at": "2026-07-07T01:00:00+00:00",
            },
            {
                "id": "memory-core",
                "user_id": "local-user",
                "memory_type": "conversation_preference",
                "content": "skip",
                "content_hash": "s",
                "created_at": "2026-07-07T01:00:00+00:00",
                "updated_at": "2026-07-07T01:00:00+00:00",
            },
        ],
        "relationship_claims": [],
    }

    stats = asyncio.run(repository.import_legacy_jsonl_snapshot(snapshot=snapshot))

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert stats["profiles"] == 1
    assert stats["platform_accounts"] == 1
    assert stats["conversations"] == 1
    assert stats["messages"] == 1
    assert stats["model_invocations"] == 1
    assert stats["persona_evaluations"] == 1
    assert stats["memories"] == 1
    assert stats["skipped_memories_without_profile"] == 1
    assert "INSERT INTO profiles" in executed_sql
    assert "INSERT INTO platform_accounts" in executed_sql
    assert "INSERT INTO conversations" in executed_sql
    assert "INSERT INTO model_invocations" in executed_sql
    assert "INSERT INTO messages" in executed_sql
    assert "INSERT INTO persona_evaluations" in executed_sql
    assert "INSERT INTO memories" in executed_sql
    assert "admin_partner" in str(repository.statements)
