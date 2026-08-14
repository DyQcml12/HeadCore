from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database_control.contracts import (
    ActorIdentity,
    DatabaseActor,
    DatabasePermissions,
    DatabaseStatus,
    SourceAccount,
)
from app.database_control.persona_persistence import InMemoryPersonaPersistenceStore
from app.database_control.persona_audit import InMemoryPersonaControlAuditSink
from app.persona_management import (
    PersistentPersonaManagementService,
    create_async_persona_management_router,
)


ADMIN_HEADERS = {
    "X-Hutao-Actor-Platform": "qq",
    "X-Hutao-Actor-User-Id": "10001",
}


class DurableTestStore(InMemoryPersonaPersistenceStore):
    @property
    def backend_name(self) -> str:
        return "durable-test-fake"

    @property
    def durable(self) -> bool:
        return True


class Access:
    def __init__(self, *, relationship: str = "admin_partner", ready: bool = True) -> None:
        self.relationship = relationship
        self.ready = ready

    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None:
        if identity.platform_user_id == "missing":
            return None
        admin = self.relationship == "admin_partner"
        return DatabaseActor(
            profile_id="profile-admin" if admin else "profile-user",
            relationship_type=self.relationship,  # type: ignore[arg-type]
            permissions=DatabasePermissions(read_admin=admin, mutate_admin=admin),
            source_account=SourceAccount(id="account", platform="qq", status="active"),
        )

    async def get_status(self) -> DatabaseStatus:
        return DatabaseStatus(
            database="hutao_chat_core",
            schema_version="v2.test",
            ready=self.ready,
            database_v2_enabled=self.ready,
            required_tables={},
            admin_exists=True,
        )


def client_for(
    store: InMemoryPersonaPersistenceStore,
    *,
    enable_writes: bool,
    ready: bool = True,
    relationship: str = "admin_partner",
    include_audit: bool = True,
) -> TestClient:
    app = FastAPI()
    access = Access(relationship=relationship, ready=ready)
    audit = InMemoryPersonaControlAuditSink() if include_audit else None
    app.state.persona_audit = audit
    app.include_router(
        create_async_persona_management_router(
            PersistentPersonaManagementService(store),
            access,
            readiness_provider=access,
            audit_sink=audit,
            enable_writes=enable_writes,
        )
    )
    return TestClient(app)


def definition_payload() -> dict[str, object]:
    return {
        "profile_id": "xiaohe_v1",
        "aliases": ["xiaohe_v1", "xiaohe"],
        "default_style": "自然、清楚、有边界",
        "core_lines": ["稳定人格是小何", "普通朋友保持边界"],
        "enabled_gates": [
            "self_harm",
            "privacy",
            "permissions",
            "response_safety",
            "legacy_identity_leak",
        ],
    }


def test_async_router_defaults_to_read_only_and_reports_not_ready() -> None:
    client = client_for(DurableTestStore(), enable_writes=False)

    status = client.get("/api/control/personas-v2/status", headers=ADMIN_HEADERS)
    create = client.post(
        "/api/control/personas-v2/drafts",
        headers=ADMIN_HEADERS,
        json={"draft_id": "draft", "definition": definition_payload()},
    )

    assert status.status_code == 200
    assert status.json()["durable"] is True
    assert status.json()["write_ready"] is False
    assert create.status_code == 503
    assert create.json()["error"]["code"] == "database_not_ready"


def test_async_router_openapi_locks_read_and_write_methods() -> None:
    paths = client_for(DurableTestStore(), enable_writes=False).get("/openapi.json").json()[
        "paths"
    ]

    assert {path: set(methods) for path, methods in paths.items()} == {
        "/api/control/personas-v2/status": {"get"},
        "/api/control/personas-v2/drafts/{draft_id}": {"get"},
        "/api/control/personas-v2/drafts/{draft_id}/validations": {"get"},
        "/api/control/personas-v2/{profile_id}/versions": {"get"},
        "/api/control/personas-v2/{profile_id}/releases": {"get"},
        "/api/control/personas-v2/bindings/all": {"get"},
        "/api/control/personas-v2/{profile_id}/runtime-projection": {"get"},
        "/api/control/personas-v2/drafts": {"post"},
        "/api/control/personas-v2/drafts/{draft_id}/validate": {"post"},
        "/api/control/personas-v2/drafts/{draft_id}/evaluations": {"post"},
        "/api/control/personas-v2/drafts/{draft_id}/approve": {"post"},
        "/api/control/personas-v2/versions/{version_id}/publish": {"post"},
        "/api/control/personas-v2/{profile_id}/rollback": {"post"},
        "/api/control/personas-v2/bindings/{binding_id}": {"put"},
    }


def test_async_router_rejects_memory_store_even_when_write_flag_is_enabled() -> None:
    response = client_for(
        InMemoryPersonaPersistenceStore(), enable_writes=True
    ).post(
        "/api/control/personas-v2/drafts",
        headers=ADMIN_HEADERS,
        json={"draft_id": "draft", "definition": definition_payload()},
    )

    assert response.status_code == 503
    assert "not durable" in response.json()["error"]["message"]


def test_async_router_rejects_writes_when_audit_sink_is_missing() -> None:
    response = client_for(
        DurableTestStore(), enable_writes=True, include_audit=False
    ).post(
        "/api/control/personas-v2/drafts",
        headers=ADMIN_HEADERS,
        json={"draft_id": "draft", "definition": definition_payload()},
    )

    assert response.status_code == 503


def test_async_router_requires_admin_and_database_readiness_for_writes() -> None:
    payload = {"draft_id": "draft", "definition": definition_payload()}
    forbidden = client_for(
        DurableTestStore(), enable_writes=True, relationship="normal_friend"
    ).post("/api/control/personas-v2/drafts", headers=ADMIN_HEADERS, json=payload)
    unavailable = client_for(
        DurableTestStore(), enable_writes=True, ready=False
    ).post("/api/control/personas-v2/drafts", headers=ADMIN_HEADERS, json=payload)

    assert forbidden.status_code == 403
    assert unavailable.status_code == 503


def test_async_router_maps_401_404_and_409_errors() -> None:
    client = client_for(DurableTestStore(), enable_writes=True)
    unauthenticated = client.get("/api/control/personas-v2/status")
    missing = client.get(
        "/api/control/personas-v2/drafts/missing", headers=ADMIN_HEADERS
    )
    mismatch = client.put(
        "/api/control/personas-v2/bindings/path-id",
        headers=ADMIN_HEADERS,
        json={
            "binding_id": "body-id",
            "scope": "global",
            "scope_key": "*",
            "version_id": "xiaohe_v1@1",
        },
    )

    assert unauthenticated.status_code == 401
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "draft_not_found"
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "binding_id_mismatch"


def test_async_router_executes_full_admin_release_flow() -> None:
    client = client_for(DurableTestStore(), enable_writes=True)
    create = client.post(
        "/api/control/personas-v2/drafts",
        headers=ADMIN_HEADERS,
        json={"draft_id": "draft", "definition": definition_payload()},
    )
    validate = client.post(
        "/api/control/personas-v2/drafts/draft/validate", headers=ADMIN_HEADERS
    )
    evaluate = client.post(
        "/api/control/personas-v2/drafts/draft/evaluations",
        headers=ADMIN_HEADERS,
        json={"stage": "regression", "passed": True},
    )
    approve = client.post(
        "/api/control/personas-v2/drafts/draft/approve", headers=ADMIN_HEADERS
    )
    publish = client.post(
        "/api/control/personas-v2/versions/xiaohe_v1@1/publish",
        headers=ADMIN_HEADERS,
        json={"operation_id": "publish-1"},
    )
    binding = client.put(
        "/api/control/personas-v2/bindings/qq",
        headers=ADMIN_HEADERS,
        json={
            "binding_id": "qq",
            "scope": "platform",
            "scope_key": "qq",
            "version_id": "xiaohe_v1@1",
            "surface": {"display_name": "QQ 小何"},
        },
    )
    projection = client.get(
        "/api/control/personas-v2/xiaohe_v1/runtime-projection",
        headers=ADMIN_HEADERS,
        params={"platform": "qq"},
    )

    assert create.status_code == 200
    assert create.json()["status"] == "draft"
    assert validate.status_code == 200
    assert all(item["passed"] for item in validate.json())
    assert evaluate.json()["status"] == "offline_evaluated"
    assert approve.json()["version_id"] == "xiaohe_v1@1"
    assert publish.json()["status"] == "active"
    assert binding.status_code == 200
    assert projection.json()["surface"] == [["display_name", "QQ 小何"]]


def test_async_router_does_not_echo_core_lines_in_management_summaries() -> None:
    client = client_for(DurableTestStore(), enable_writes=True)
    response = client.post(
        "/api/control/personas-v2/drafts",
        headers=ADMIN_HEADERS,
        json={"draft_id": "draft", "definition": definition_payload()},
    )

    assert response.status_code == 200
    assert "core_lines" not in response.json()
    assert "definition" not in response.json()


def test_async_router_audits_success_and_rejections_without_payload_content() -> None:
    client = client_for(DurableTestStore(), enable_writes=True)
    secret_marker = "PRIVATE_CORE_LINE_MUST_NOT_ENTER_AUDIT"
    payload = definition_payload()
    payload["core_lines"] = [secret_marker]
    accepted = client.post(
        "/api/control/personas-v2/drafts",
        headers=ADMIN_HEADERS,
        json={"draft_id": "draft", "definition": payload},
    )
    conflict = client.post(
        "/api/control/personas-v2/drafts",
        headers=ADMIN_HEADERS,
        json={"draft_id": "draft", "definition": payload},
    )

    audit = client.app.state.persona_audit
    events = asyncio.run(audit.list_events())

    assert accepted.status_code == 200
    assert conflict.status_code == 409
    assert [(event.status, event.reason_code) for event in events] == [
        ("accepted", "completed"),
        ("rejected", "conflict"),
    ]
    assert all(event.actor_profile_id == "profile-admin" for event in events)
    assert secret_marker not in repr(events)


def test_async_router_audits_permission_and_readiness_rejections() -> None:
    payload = {"draft_id": "draft", "definition": definition_payload()}
    forbidden_client = client_for(
        DurableTestStore(), enable_writes=True, relationship="normal_friend"
    )
    unavailable_client = client_for(DurableTestStore(), enable_writes=True, ready=False)

    forbidden_client.post(
        "/api/control/personas-v2/drafts", headers=ADMIN_HEADERS, json=payload
    )
    unavailable_client.post(
        "/api/control/personas-v2/drafts", headers=ADMIN_HEADERS, json=payload
    )

    forbidden_events = asyncio.run(forbidden_client.app.state.persona_audit.list_events())
    unavailable_events = asyncio.run(unavailable_client.app.state.persona_audit.list_events())
    assert forbidden_events[0].reason_code == "admin_required"
    assert unavailable_events[0].reason_code == "database_not_ready"
