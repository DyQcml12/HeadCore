from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.operations.aggregation import OperationsStatusService
from app.operations.audit import InMemoryOperationAudit, OperationPermissionError
from app.operations.contracts import ComponentState, ComponentStatus, DependencyStatus
from app.operations.redaction import config_presence, redact_text
from app.operations.reports import summarize_test_report
from app.operations.observability import classify_error_lines
from app.operations.probes import HttpStatusProvider, StaticStatusProvider
from app.operations.project_status import DatabaseControlStatusProvider, asr_model_readiness
from app.database_control.contracts import DatabaseStatus
from app.database_control.contracts import ActorIdentity, DatabaseActor, DatabasePermissions, SourceAccount
from app.database_control.errors import ForbiddenError
from app.operations.control_write import ControlWriteGuard
from app.operations.system_contract_status import ChannelContractStatusProvider, PersonaManagementStatusProvider, ProviderRegistryStatusProvider
from app.persona_management.contracts import PersonaManagementStatus
from app.providers.contracts import ProviderCapability, ProviderHealth, ProviderId
from app.providers.registry import ProviderRegistry


@dataclass
class FakeProvider:
    component_id: str
    status: ComponentStatus
    delay: float = 0
    error: Exception | None = None

    async def get_status(self) -> ComponentStatus:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.status


def status(component_id: str, state: ComponentState = ComponentState.ONLINE, **kwargs) -> ComponentStatus:
    return ComponentStatus(
        component_id=component_id,
        label=component_id,
        category="service",
        state=state,
        **kwargs,
    )


def test_aggregate_propagates_dependency_degradation() -> None:
    providers = [
        FakeProvider("database", status("database", ComponentState.OFFLINE)),
        FakeProvider(
            "api",
            status(
                "api",
                dependencies=(DependencyStatus("database", ComponentState.ONLINE),),
            ),
        ),
    ]

    snapshot = asyncio.run(OperationsStatusService(providers).snapshot())

    assert snapshot.state is ComponentState.DEGRADED
    assert snapshot.components["api"].state is ComponentState.DEGRADED
    assert snapshot.components["api"].detail == "blocked by: database"


def test_provider_timeout_does_not_block_other_components() -> None:
    providers = [
        FakeProvider("slow", status("slow"), delay=0.1),
        FakeProvider("fast", status("fast")),
    ]

    snapshot = asyncio.run(OperationsStatusService(providers, timeout_seconds=0.01).snapshot())

    assert snapshot.components["fast"].state is ComponentState.ONLINE
    assert snapshot.components["slow"].state is ComponentState.DEGRADED
    assert "timed out" in snapshot.components["slow"].detail


def test_provider_exception_is_classified_without_message_leak() -> None:
    provider = FakeProvider("model", status("model"), error=RuntimeError("token=private-value"))

    snapshot = asyncio.run(OperationsStatusService([provider]).snapshot())

    detail = snapshot.components["model"].detail
    assert detail == "status check failed: RuntimeError"
    assert "private-value" not in detail


def test_redaction_and_config_presence_never_return_values() -> None:
    text = "api_key=sk-abcdefgh12345678 token: abc123 password=hunter2 Authorization=BearerXYZ"

    redacted = redact_text(text)
    statuses = config_presence({"API_KEY": "secret", "OPTIONAL": "  "})

    assert "abcdefgh" not in redacted
    assert "abc123" not in redacted
    assert "hunter2" not in redacted
    assert [(item.name, item.configured) for item in statuses] == [("API_KEY", True), ("OPTIONAL", False)]
    assert all(not hasattr(item, "value") for item in statuses)


def test_non_admin_write_has_403_semantics() -> None:
    audit = InMemoryOperationAudit()

    with pytest.raises(OperationPermissionError) as exc_info:
        audit.record(action="service.start", actor_id="friend", is_admin=False, success=True)

    assert exc_info.value.status_code == 403
    assert audit.list_records() == ()


def test_admin_operation_is_audited_and_reason_is_redacted() -> None:
    audit = InMemoryOperationAudit()

    result = audit.record(
        action="service.stop",
        actor_id="owner",
        is_admin=True,
        success=False,
        reason="token=secret-token failed",
    )

    assert result.audit_id
    assert result.actor_id == "owner"
    assert "secret-token" not in result.reason
    assert audit.list_records() == (result,)


def test_report_summary_supports_windows_path_and_utf8(tmp_path: Path) -> None:
    report = tmp_path / "测试 reports" / "all.test-report.md"
    report.parent.mkdir()
    report.write_text("# 测试结果\n\n351 passed, 2 failed\n", encoding="utf-8")

    summary = summarize_test_report(report, root=tmp_path)

    assert summary.passed == 351
    assert summary.failed == 2
    assert summary.state is ComponentState.DEGRADED
    assert summary.report_path == "测试 reports/all.test-report.md"


def test_report_summary_handles_missing_and_corrupt_files(tmp_path: Path) -> None:
    missing = summarize_test_report(tmp_path / "missing.md", root=tmp_path)
    corrupt_path = tmp_path / "corrupt.md"
    corrupt_path.write_bytes(b"\xff\xfe\x00")
    corrupt = summarize_test_report(corrupt_path, root=tmp_path)

    assert missing.state is ComponentState.MISSING
    assert corrupt.state is ComponentState.DEGRADED
    assert corrupt.passed == 0


def test_static_provider_distinguishes_not_configured_and_not_ready() -> None:
    missing = StaticStatusProvider("db", "Database", "database", configured=False, ready=False)
    unready = StaticStatusProvider("model", "Model", "provider", configured=True, ready=False)

    snapshot = asyncio.run(OperationsStatusService([missing, unready]).snapshot())

    assert snapshot.components["db"].state is ComponentState.NOT_CONFIGURED
    assert snapshot.components["model"].state is ComponentState.DEGRADED


def test_http_probe_uses_get_without_model_or_platform_side_effects(monkeypatch) -> None:
    seen = {}

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    def fake_urlopen(request, timeout):
        seen["method"] = request.method
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.operations.probes.urllib.request.urlopen", fake_urlopen)
    provider = HttpStatusProvider("core", "Core", "http://127.0.0.1:8000/health")

    result = asyncio.run(provider.get_status())

    assert result.state is ComponentState.ONLINE
    assert seen == {"method": "GET", "timeout": 0.5}


def test_recent_errors_are_classified_without_retaining_log_content() -> None:
    summaries = classify_error_lines(
        ["provider timed out token=secret", "HTTP 429 Too Many Requests", "unexpected failure"]
    )

    assert [(item.category, item.count) for item in summaries] == [
        ("rate_limit", 1),
        ("timeout", 1),
        ("unknown", 1),
    ]
    assert all(not hasattr(item, "line") for item in summaries)


def test_database_control_provider_uses_public_status_contract() -> None:
    class Repository:
        async def get_status(self) -> DatabaseStatus:
            return DatabaseStatus(
                database="hutao_chat_core",
                schema_version="v2.001_hutao_chat_core_schema",
                ready=False,
                database_v2_enabled=True,
                required_tables={"profiles": True, "messages": False},
                admin_exists=True,
            )

    result = asyncio.run(DatabaseControlStatusProvider(Repository()).get_status())  # type: ignore[arg-type]

    assert result.state is ComponentState.DEGRADED
    assert result.detail == "readiness failed; missing tables: 1"


def test_asr_readiness_checks_local_models_without_loading_them(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "sensevoice"
    model.mkdir()
    monkeypatch.setattr("app.operations.project_status.resolve_modelscope_model", lambda value: str(model))

    configured, ready, detail = asr_model_readiness("sensevoice-small")
    unknown = asr_model_readiness("unknown-preset")

    assert (configured, ready) == (True, True)
    assert "sensevoice-small" in detail
    assert unknown[0:2] == (False, False)


class ControlWriteRepositoryFake:
    def __init__(self, actor: DatabaseActor | None) -> None:
        self.actor = actor
        self.records = []

    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None:
        return self.actor

    async def record_control_operation(self, **kwargs) -> None:
        self.records.append(kwargs)


def control_actor(relationship: str = "admin_partner") -> DatabaseActor:
    allowed = relationship == "admin_partner"
    return DatabaseActor(
        profile_id="profile-1",
        relationship_type=relationship,  # type: ignore[arg-type]
        permissions=DatabasePermissions(read_admin=allowed, mutate_admin=allowed),
        source_account=SourceAccount(id="account-1", platform="qq", status="active"),
    )


def test_control_write_guard_authorizes_database_resolved_admin() -> None:
    repository = ControlWriteRepositoryFake(control_actor())
    guard = ControlWriteGuard(repository)

    actor = asyncio.run(guard.authorize(platform="qq", user_id="123", group_id=None, operation="service_start"))
    asyncio.run(guard.record_result(actor=actor, operation="service_start", success=True, reason_code="completed"))

    assert repository.records[0]["status"] == "accepted"
    assert repository.records[0]["actor"] == actor


@pytest.mark.parametrize("resolved_actor", [None, control_actor("normal_friend")])
def test_control_write_guard_rejects_and_audits_non_admin(resolved_actor) -> None:
    repository = ControlWriteRepositoryFake(resolved_actor)
    guard = ControlWriteGuard(repository)

    with pytest.raises(ForbiddenError):
        asyncio.run(guard.authorize(platform="qq", user_id="123", group_id=None, operation="config_update"))

    assert repository.records[0]["status"] == "rejected"
    assert repository.records[0]["reason_code"] == "admin_required"


def test_control_write_guard_rejects_missing_headers() -> None:
    repository = ControlWriteRepositoryFake(None)
    guard = ControlWriteGuard(repository)

    with pytest.raises(ForbiddenError):
        asyncio.run(guard.authorize(platform=None, user_id=None, group_id=None, operation="test_run"))

    assert repository.records[0]["platform"] == "core"


def test_control_write_guard_verify_has_no_audit_side_effect() -> None:
    repository = ControlWriteRepositoryFake(control_actor())
    actor = asyncio.run(ControlWriteGuard(repository).verify(platform="qq", user_id="123", group_id=None))
    assert actor is not None
    assert repository.records == []


def test_control_write_guard_allows_configured_fallback_admin_when_database_is_unavailable() -> None:
    class UnavailableRepository(ControlWriteRepositoryFake):
        async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None:
            raise RuntimeError("database is disabled")

    repository = UnavailableRepository(None)
    guard = ControlWriteGuard(repository, fallback_admin_accounts={"qq": {"10001"}})

    actor = asyncio.run(
        guard.authorize(platform="qq", user_id="10001", group_id=None, operation="service_start")
    )

    assert actor.profile_id == "bootstrap-admin"
    assert actor.permissions.mutate_admin is True
    assert actor.source_account.platform == "qq"


def test_control_write_guard_rejects_unknown_fallback_identity() -> None:
    repository = ControlWriteRepositoryFake(None)
    guard = ControlWriteGuard(repository, fallback_admin_accounts={"qq": {"10001"}})

    with pytest.raises(ForbiddenError):
        asyncio.run(
            guard.authorize(platform="qq", user_id="99999", group_id=None, operation="service_start")
        )


def test_channel_contract_status_uses_public_capabilities() -> None:
    result = asyncio.run(ChannelContractStatusProvider().get_status())
    assert result.state is ComponentState.ONLINE
    assert result.detail == "Core API text=True"


def test_persona_management_status_maps_memory_backend_to_degraded() -> None:
    provider = PersonaManagementStatusProvider(lambda: PersonaManagementStatus(storage_backend="memory", durable=False, write_ready=False, draft_count=0, version_count=0, release_count=0, binding_count=0, active_profiles=()))
    result = asyncio.run(provider.get_status())
    assert result.state is ComponentState.DEGRADED
    assert "backend=memory" in result.detail


def test_provider_registry_status_maps_public_health() -> None:
    class Provider:
        provider_id = ProviderId("demo")
        capabilities = frozenset({ProviderCapability.TEXT})

    registry = ProviderRegistry()
    registry.register(Provider())
    registry.set_health("demo", ProviderHealth.CIRCUIT_OPEN)
    result = asyncio.run(ProviderRegistryStatusProvider(registry, "demo").get_status())
    assert result.state is ComponentState.DEGRADED
    assert result.detail == "health=circuit_open"
