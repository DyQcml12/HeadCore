from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database_control.contracts import (
    ActorIdentity,
    DatabaseActor,
    DatabasePermissions,
    SourceAccount,
)
from app.persona_management import (
    BindingScope,
    InMemoryPersonaManagementService,
    PersonaBinding,
    PersonaValidationResult,
    ValidationStage,
    create_persona_management_router,
)
from tests.persona_management.test_persona_management import xiaohe_definition


ADMIN_HEADERS = {
    "X-Hutao-Actor-Platform": "qq",
    "X-Hutao-Actor-User-Id": "10001",
}


class ActorResolver:
    def __init__(self, relationship_type: str = "admin_partner") -> None:
        self.relationship_type = relationship_type

    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None:
        if identity.platform_user_id == "missing":
            return None
        is_admin = self.relationship_type == "admin_partner"
        return DatabaseActor(
            profile_id="admin-profile",
            relationship_type=self.relationship_type,  # type: ignore[arg-type]
            permissions=DatabasePermissions(read_admin=is_admin, mutate_admin=is_admin),
            source_account=SourceAccount(id="account", platform="qq", status="active"),
        )


def published_service() -> InMemoryPersonaManagementService:
    service = InMemoryPersonaManagementService()
    service.create_draft(xiaohe_definition(), actor_id="author", draft_id="draft")
    service.validate_draft("draft")
    service.record_evaluation(
        "draft",
        PersonaValidationResult(stage=ValidationStage.REGRESSION, passed=True),
    )
    version = service.approve("draft", actor_id="reviewer")
    service.publish(version.version_id, actor_id="operator")
    service.save_binding(
        PersonaBinding(
            binding_id="qq",
            scope=BindingScope.PLATFORM,
            scope_key="qq",
            version_id=version.version_id,
            surface=(("display_name", "QQ 小何"),),
        )
    )
    return service


def client_for(
    service: InMemoryPersonaManagementService,
    relationship_type: str = "admin_partner",
) -> TestClient:
    app = FastAPI()
    app.include_router(create_persona_management_router(service, ActorResolver(relationship_type)))
    return TestClient(app)


def test_router_exposes_read_only_openapi_contract() -> None:
    paths = client_for(published_service()).get("/openapi.json").json()["paths"]

    assert set(paths) == {
        "/api/control/personas/status",
        "/api/control/personas/{profile_id}/versions",
        "/api/control/personas/{profile_id}/releases",
        "/api/control/personas/versions/{version_id}",
        "/api/control/personas/bindings/all",
        "/api/control/personas/{profile_id}/runtime-projection",
    }
    assert all(set(methods) == {"get"} for methods in paths.values())


def test_router_requires_resolved_admin_actor() -> None:
    client = client_for(published_service())
    missing_headers = client.get("/api/control/personas/xiaohe_v1/versions")
    unresolved = client.get(
        "/api/control/personas/xiaohe_v1/versions",
        headers={"X-Hutao-Actor-Platform": "qq", "X-Hutao-Actor-User-Id": "missing"},
    )
    forbidden = client_for(published_service(), "normal_friend").get(
        "/api/control/personas/xiaohe_v1/versions", headers=ADMIN_HEADERS
    )

    assert missing_headers.status_code == 401
    assert unresolved.status_code == 401
    assert forbidden.status_code == 403


def test_router_returns_versions_releases_bindings_and_projection() -> None:
    client = client_for(published_service())

    versions = client.get("/api/control/personas/xiaohe_v1/versions", headers=ADMIN_HEADERS)
    releases = client.get("/api/control/personas/xiaohe_v1/releases", headers=ADMIN_HEADERS)
    bindings = client.get("/api/control/personas/bindings/all", headers=ADMIN_HEADERS)
    projection = client.get(
        "/api/control/personas/xiaohe_v1/runtime-projection",
        params={"platform": "qq"},
        headers=ADMIN_HEADERS,
    )
    status = client.get("/api/control/personas/status", headers=ADMIN_HEADERS)

    assert versions.status_code == 200
    assert versions.json()[0]["version_id"] == "xiaohe_v1@1"
    assert releases.status_code == 200
    assert releases.json()[0]["status"] == "active"
    assert bindings.json()[0]["binding_id"] == "qq"
    assert projection.status_code == 200
    assert projection.json()["profile_id"] == "xiaohe_v1"
    assert projection.json()["surface"] == [["display_name", "QQ 小何"]]
    assert status.status_code == 200
    assert status.json() == {
        "storage_backend": "memory",
        "durable": False,
        "write_ready": False,
        "draft_count": 1,
        "version_count": 1,
        "release_count": 1,
        "binding_count": 1,
        "active_profiles": ["xiaohe_v1"],
    }


def test_router_returns_404_for_missing_version_and_projection() -> None:
    client = client_for(InMemoryPersonaManagementService())

    version = client.get("/api/control/personas/versions/missing", headers=ADMIN_HEADERS)
    projection = client.get(
        "/api/control/personas/missing/runtime-projection", headers=ADMIN_HEADERS
    )

    assert version.status_code == 404
    assert version.json()["error"]["code"] == "version_not_found"
    assert projection.status_code == 404
    assert projection.json()["error"]["code"] == "active_version_not_found"
