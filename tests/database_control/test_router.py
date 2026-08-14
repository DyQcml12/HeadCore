from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database_control.errors import ResourceConflictError
from app.database_control.router import create_database_control_router
from app.database_control.service import DatabaseControlService
from tests.database_control.fakes import FakeDatabaseControlRepository, actor


ADMIN_HEADERS = {
    "X-Hutao-Actor-Platform": "qq",
    "X-Hutao-Actor-User-Id": "10001",
}


def client_for(repository: FakeDatabaseControlRepository) -> TestClient:
    app = FastAPI()
    app.include_router(create_database_control_router(DatabaseControlService(repository)))
    return TestClient(app)


def test_router_exposes_read_and_write_openapi_contract() -> None:
    client = client_for(FakeDatabaseControlRepository(actor()))
    paths = client.get("/openapi.json").json()["paths"]

    expected_methods = {
        "/api/control/database-v2/status": {"get"},
        "/api/control/database-v2/admin": {"get"},
        "/api/control/database-v2/profiles": {"get"},
        "/api/control/database-v2/profiles/{profile_id}": {"get"},
        "/api/control/database-v2/bootstrap-admin": {"post"},
        "/api/control/database-v2/profiles/{profile_id}/relationship": {"post"},
        "/api/control/database-v2/platform-accounts/bind": {"post"},
        "/api/control/database-v2/claims/{claim_id}/approve": {"post"},
        "/api/control/database-v2/claims/{claim_id}/reject": {"post"},
    }
    assert set(paths) == set(expected_methods)
    assert all(set(paths[path]) == methods for path, methods in expected_methods.items())


def test_router_returns_401_when_actor_headers_are_missing() -> None:
    response = client_for(FakeDatabaseControlRepository(actor())).get(
        "/api/control/database-v2/status"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_router_returns_403_for_non_admin_database_actor() -> None:
    response = client_for(FakeDatabaseControlRepository(actor("normal_friend"))).get(
        "/api/control/database-v2/profiles",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"


def test_router_returns_status_and_filtered_profile_page() -> None:
    repository = FakeDatabaseControlRepository(actor())
    client = client_for(repository)

    status = client.get("/api/control/database-v2/status", headers=ADMIN_HEADERS)
    profiles = client.get(
        "/api/control/database-v2/profiles",
        params={"relationship_type": "normal_friend", "platform": "qq", "limit": 25},
        headers=ADMIN_HEADERS,
    )

    assert status.status_code == 200
    assert status.json()["ready"] is True
    assert profiles.status_code == 200
    assert profiles.json()["next_cursor"] == "cursor-2"
    assert repository.last_filters is not None
    assert repository.last_filters.relationship_type == "normal_friend"


def test_router_redacts_accounts_and_returns_404() -> None:
    client = client_for(FakeDatabaseControlRepository(actor()))
    admin = client.get("/api/control/database-v2/admin", headers=ADMIN_HEADERS)
    missing = client.get(
        "/api/control/database-v2/profiles/missing",
        headers=ADMIN_HEADERS,
    )

    assert admin.status_code == 200
    assert admin.json()["accounts"][0]["platform_user_id"] == "12*****89"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_router_maps_domain_conflict_to_409() -> None:
    class ConflictRepository(FakeDatabaseControlRepository):
        async def get_admin_profile(self):  # type: ignore[no-untyped-def]
            raise ResourceConflictError("admin profile state is inconsistent")

    response = client_for(ConflictRepository(actor())).get(
        "/api/control/database-v2/admin",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_main_application_registers_database_control_router() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/control/database-v2/status" in paths
    assert "/api/control/database-v2/profiles/{profile_id}" in paths


def test_router_applies_write_readiness_gate() -> None:
    response = client_for(FakeDatabaseControlRepository(actor(), ready=False)).post(
        "/api/control/database-v2/profiles/profile-user/relationship",
        headers=ADMIN_HEADERS,
        json={
            "relationship_type": "blocked",
            "verified": True,
            "reason": "confirmed spam",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_not_ready"


def test_router_executes_authorized_write_endpoints() -> None:
    client = client_for(FakeDatabaseControlRepository(actor()))
    relationship = client.post(
        "/api/control/database-v2/profiles/profile-user/relationship",
        headers=ADMIN_HEADERS,
        json={
            "relationship_type": "blocked",
            "verified": True,
            "reason": "confirmed spam",
        },
    )
    bind = client.post(
        "/api/control/database-v2/platform-accounts/bind",
        headers=ADMIN_HEADERS,
        json={
            "source": {"platform": "qq", "platform_user_id": "10002"},
            "target": {"platform": "wechat", "platform_user_id": "wxid_2"},
            "confirm_merge": True,
            "reason": "same person",
        },
    )
    approve = client.post(
        "/api/control/database-v2/claims/claim-1/approve",
        headers=ADMIN_HEADERS,
    )

    assert relationship.status_code == 200
    assert relationship.json()["new_relationship_type"] == "blocked"
    assert bind.status_code == 200
    assert bind.json()["status"] == "bound"
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"


def test_router_maps_database_connection_error_without_leaking_details() -> None:
    class UnavailableRepository(FakeDatabaseControlRepository):
        async def get_status(self):  # type: ignore[no-untyped-def]
            raise ConnectionError("mysql host=private-db password=secret")

    response = client_for(UnavailableRepository(actor())).get(
        "/api/control/database-v2/status",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "private-db" not in response.text
    assert "secret" not in response.text


def test_router_maps_database_integrity_error_to_conflict() -> None:
    class IntegrityError(Exception):
        pass

    class ConflictRepository(FakeDatabaseControlRepository):
        async def get_admin_profile(self):  # type: ignore[no-untyped-def]
            raise IntegrityError("duplicate key contains private value")

    response = client_for(ConflictRepository(actor())).get(
        "/api/control/database-v2/admin",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "private value" not in response.text
