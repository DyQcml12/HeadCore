import asyncio

import pytest

from app.core.config import load_settings
from app.database_control.contracts import (
    AccountIdentityInput,
    ActorIdentity,
    BindAccountsRequest,
    BootstrapAdminRequest,
    ProfileFilters,
)
from app.database_control.errors import ForbiddenError, ResourceConflictError
from app.database_control.mysql_adapter import MySQLDatabaseControlAdapter
from app.storage.v2_models import (
    V2PlatformAccount,
    V2Profile,
    build_relationship_context,
)
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository
from tests.database_control.fakes import actor


def relationship_context():
    return build_relationship_context(
        profile=V2Profile(
            id="profile-admin",
            display_name="管理员",
            relationship_type="admin_partner",
            verified=True,
            trust_level=100,
            affection_level=100,
            notes="",
            status="active",
            merged_into_profile_id=None,
            created_at="2026-07-14 08:00:00",
            updated_at="2026-07-14 08:00:00",
        ),
        platform_account=V2PlatformAccount(
            id="account-admin",
            profile_id="profile-admin",
            platform="qq",
            platform_user_id="10001",
            platform_group_id="",
            display_name="管理员",
            account_label="main",
            is_primary=True,
            status="active",
            confidence=100,
            verified_by_profile_id="profile-admin",
            last_seen_at="2026-07-14 08:00:00",
            created_at="2026-07-14 08:00:00",
            updated_at="2026-07-14 08:00:00",
        ),
    )


def profile_row(profile_id: str, updated_at: str) -> dict[str, object]:
    return {
        "id": profile_id,
        "display_name": "测试用户",
        "relationship_type": "normal_friend",
        "verified": False,
        "trust_level": 10,
        "affection_level": 10,
        "status": "active",
        "merged_into_profile_id": None,
        "account_count": 1,
        "last_seen_at": updated_at,
        "labels_text": "friend:同学",
        "updated_at": updated_at,
    }


class FakeV2ControlStorage:
    def __init__(self, *, admin_exists: bool = True) -> None:
        self.context = relationship_context()
        self.list_calls: list[dict[str, object]] = []
        self.admin_exists = admin_exists
        self.audit_events: list[dict[str, object]] = []
        self.claim_result: dict[str, object] = {"status": "approved", "claim_id": "claim-1"}

    async def find_relationship_context(self, **kwargs):  # type: ignore[no-untyped-def]
        return self.context

    async def get_control_status_snapshot(self, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "schema_version": "v2.001_hutao_chat_core_schema",
            "tables": {"profiles", "platform_accounts", "admin_profile", "conversations", "messages"},
            "admin_exists": self.admin_exists,
        }

    async def list_profile_snapshots(self, **kwargs):  # type: ignore[no-untyped-def]
        self.list_calls.append(kwargs)
        return [
            profile_row("profile-3", "2026-07-14 09:00:00"),
            profile_row("profile-2", "2026-07-14 08:00:00"),
            profile_row("profile-1", "2026-07-14 07:00:00"),
        ]

    async def bootstrap_admin_if_missing(self, **kwargs):  # type: ignore[no-untyped-def]
        return None if self.admin_exists else "profile-admin"

    async def bind_accounts(self, **kwargs):  # type: ignore[no-untyped-def]
        return "profile-source"

    async def approve_relationship_claim(self, **kwargs):  # type: ignore[no-untyped-def]
        return self.claim_result

    async def reject_relationship_claim(self, **kwargs):  # type: ignore[no-untyped-def]
        return self.claim_result

    async def record_database_control_event(self, **kwargs):  # type: ignore[no-untyped-def]
        self.audit_events.append(kwargs)

    async def list_database_control_events(self, **kwargs):  # type: ignore[no-untyped-def]
        return [{"id": "audit-1", "command_name": "service_start", "platform": "qq", "status": "accepted", "reason_code": "completed", "created_at": "2026-07-15 00:00:00"}]


def adapter(storage: FakeV2ControlStorage) -> MySQLDatabaseControlAdapter:
    settings = load_settings()
    object.__setattr__(settings, "mysql_database", "hutao_chat_core")
    object.__setattr__(settings, "database_v2_enabled", True)
    return MySQLDatabaseControlAdapter(settings, storage)  # type: ignore[arg-type]


def test_adapter_projects_safe_control_audit_fields() -> None:
    events = asyncio.run(adapter(FakeV2ControlStorage()).list_control_operations(limit=10))

    assert events[0].audit_id == "audit-1"
    assert events[0].operation == "service_start"
    assert not hasattr(events[0], "actor_profile_id")


def test_mysql_adapter_maps_database_actor_and_ready_status() -> None:
    control = adapter(FakeV2ControlStorage())

    actor = asyncio.run(
        control.resolve_actor(ActorIdentity(platform="qq", platform_user_id="10001"))
    )
    status = asyncio.run(control.get_status())

    assert actor is not None
    assert actor.permissions.read_admin is True
    assert actor.source_account.id == "account-admin"
    assert status.ready is True
    assert status.database_v2_enabled is True


def test_mysql_adapter_uses_opaque_stable_cursor() -> None:
    storage = FakeV2ControlStorage()
    control = adapter(storage)
    first = asyncio.run(
        control.list_profiles(filters=ProfileFilters(), limit=2, cursor=None)
    )

    assert [item.id for item in first.items] == ["profile-3", "profile-2"]
    assert first.next_cursor is not None

    asyncio.run(
        control.list_profiles(filters=ProfileFilters(), limit=2, cursor=first.next_cursor)
    )
    assert storage.list_calls[-1]["cursor_updated_at"] == "2026-07-14 08:00:00"
    assert storage.list_calls[-1]["cursor_profile_id"] == "profile-2"


def test_mysql_adapter_rejects_invalid_cursor() -> None:
    with pytest.raises(ResourceConflictError):
        asyncio.run(
            adapter(FakeV2ControlStorage()).list_profiles(
                filters=ProfileFilters(), limit=10, cursor="not-a-cursor"
            )
        )


def test_mysql_adapter_bootstrap_requires_configured_owner_identity() -> None:
    storage = FakeV2ControlStorage(admin_exists=False)
    control = adapter(storage)
    object.__setattr__(control._settings, "owner_bootstrap_qq_ids", "10001")

    created = asyncio.run(
        control.bootstrap_admin(
            BootstrapAdminRequest(display_name="admin", qq_ids=["10001"]),
            local_request=True,
        )
    )
    assert created.created is True
    assert created.bound_accounts[0].platform_user_id != "10001"

    with pytest.raises(ForbiddenError):
        asyncio.run(
            control.bootstrap_admin(
                BootstrapAdminRequest(display_name="admin", qq_ids=["attacker"]),
                local_request=True,
            )
        )


def test_mysql_adapter_requires_merge_confirmation_and_audits_rejection() -> None:
    storage = FakeV2ControlStorage()
    target_context = relationship_context()
    object.__setattr__(target_context.profile, "id", "profile-target")

    async def find_context(**kwargs):  # type: ignore[no-untyped-def]
        return storage.context if kwargs["platform"] == "qq" else target_context

    storage.find_relationship_context = find_context  # type: ignore[method-assign]
    control = adapter(storage)
    request = BindAccountsRequest(
        source=AccountIdentityInput(platform="qq", platform_user_id="10001"),
        target=AccountIdentityInput(platform="wechat", platform_user_id="wxid_1"),
        confirm_merge=False,
        reason="same person",
    )

    with pytest.raises(ResourceConflictError):
        asyncio.run(control.bind_accounts(actor=actor(), request=request))

    assert storage.audit_events[-1]["status"] == "rejected"
    assert storage.audit_events[-1]["reason_code"] == "merge_confirmation_required"


def test_mysql_adapter_maps_already_reviewed_claim_to_conflict_and_audit() -> None:
    storage = FakeV2ControlStorage()
    storage.claim_result = {"status": "already_reviewed", "claim_id": "claim-1"}

    with pytest.raises(ResourceConflictError):
        asyncio.run(
            adapter(storage).review_claim(actor=actor(), claim_id="claim-1", approve=True)
        )

    assert storage.audit_events[-1]["reason_code"] == "already_reviewed"


class ReadOnlyRecordingRepository(MySQLDatabaseV2Repository):
    def __init__(self) -> None:
        settings = load_settings()
        object.__setattr__(settings, "mysql_database", "hutao_chat_core")
        object.__setattr__(settings, "mysql_user", "test-user")
        object.__setattr__(settings, "mysql_password", "test-password")
        super().__init__(settings)
        self.statements: list[str] = []
        self.fetchone_results: list[dict[str, object] | None] = []
        self.fetchall_results: list[list[dict[str, object]]] = []

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:
        raise AssertionError("control-plane read operation attempted a write")

    async def _fetchone(self, sql: str, params: tuple[object, ...]):  # type: ignore[no-untyped-def]
        self.statements.append(sql)
        return self.fetchone_results.pop(0) if self.fetchone_results else None

    async def _fetchall(self, sql: str, params: tuple[object, ...]):  # type: ignore[no-untyped-def]
        self.statements.append(sql)
        return self.fetchall_results.pop(0) if self.fetchall_results else []


class WriteRecordingRepository(ReadOnlyRecordingRepository):
    def __init__(self) -> None:
        super().__init__()
        self.writes: list[tuple[str, tuple[object, ...]]] = []

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:
        self.writes.append((sql, params))
        return 1


def test_mysql_repository_control_queries_are_read_only() -> None:
    repository = ReadOnlyRecordingRepository()
    repository.fetchone_results = [
        {"version": "v2.001_hutao_chat_core_schema"},
        {"profile_id": "profile-admin"},
    ]
    repository.fetchall_results = [[
        {"TABLE_NAME": "profiles"},
        {"TABLE_NAME": "admin_profile"},
        {"TABLE_NAME": "schema_migrations"},
    ]]

    snapshot = asyncio.run(
        repository.get_control_status_snapshot(
            required_tables=("profiles", "platform_accounts", "admin_profile", "conversations", "messages")
        )
    )

    assert snapshot["admin_exists"] is True
    assert all("SELECT" in sql for sql in repository.statements)


def test_mysql_repository_status_tolerates_unmigrated_database() -> None:
    repository = ReadOnlyRecordingRepository()
    repository.fetchall_results = [[]]

    snapshot = asyncio.run(
        repository.get_control_status_snapshot(
            required_tables=("profiles", "platform_accounts", "admin_profile", "conversations", "messages")
        )
    )

    assert snapshot == {"schema_version": "", "tables": set(), "admin_exists": False}
    assert len(repository.statements) == 1


def test_mysql_repository_relationship_write_and_control_audit_are_persisted() -> None:
    repository = WriteRecordingRepository()
    repository.fetchone_results = [
        {
            "id": "profile-user",
            "relationship_type": "normal_friend",
            "verified": False,
            "status": "active",
        },
        {"profile_id": "profile-admin"},
    ]

    result = asyncio.run(
        repository.update_profile_relationship(
            profile_id="profile-user",
            relationship_type="blocked",
            verified=True,
            changed_by_profile_id="profile-admin",
            reason="confirmed spam",
        )
    )
    asyncio.run(
        repository.record_database_control_event(
            actor_profile_id="profile-admin",
            platform="qq",
            command_name="set_profile_relationship",
            status="accepted",
            reason_code="updated",
            details={"token": "sk-123456789012345678901234"},
        )
    )

    sql = "\n".join(statement for statement, _params in repository.writes)
    assert result["status"] == "updated"
    assert "UPDATE profiles" in sql
    assert "INSERT INTO relationship_events" in sql
    assert "INSERT INTO platform_command_events" in sql
    assert "<REDACTED_API_KEY>" in str(repository.writes[-1][1])
