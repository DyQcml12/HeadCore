import asyncio

from fastapi import FastAPI, Request

from app.database_control.integration_guard import validate_isolated_test_database
from scripts import database_control_smoke


def test_integration_database_guard_accepts_only_explicit_test_names() -> None:
    assert validate_isolated_test_database("test_hutao_control") == "test_hutao_control"
    assert validate_isolated_test_database("hutao_control_test") == "hutao_control_test"

    for unsafe in ("", "hutao_chat_core", "production_test_backup"):
        try:
            validate_isolated_test_database(unsafe)
        except ValueError as exc:
            assert "integration" in str(exc)
        else:
            raise AssertionError(f"unsafe integration database was accepted: {unsafe}")


def smoke_app(calls: list[str]) -> FastAPI:
    app = FastAPI()

    @app.get("/api/control/database-v2/status")
    async def status() -> dict[str, object]:
        calls.append("GET status")
        return {"ready": True}

    @app.get("/api/control/database-v2/admin")
    async def admin() -> dict[str, object]:
        calls.append("GET admin")
        return {
            "profile": {
                "id": "profile-admin",
                "relationship_type": "admin_partner",
                "verified": True,
            }
        }

    @app.get("/api/control/database-v2/profiles")
    async def profiles() -> dict[str, object]:
        calls.append("GET profiles")
        return {"items": []}

    @app.post("/api/control/database-v2/profiles/{profile_id}/relationship")
    async def relationship(profile_id: str, request: Request) -> dict[str, object]:
        calls.append(f"POST relationship {profile_id}")
        return await request.json()

    return app


def test_database_control_smoke_defaults_to_read_only(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(database_control_smoke, "app", smoke_app(calls))

    report = asyncio.run(
        database_control_smoke.run_database_control_smoke(
            actor_platform="qq",
            actor_user_id="123456789",
            output_root=tmp_path,
        )
    )
    text = report.read_text(encoding="utf-8")

    assert calls == ["GET status", "GET admin", "GET profiles"]
    assert "Mode: read-only" in text
    assert "123456789" not in text
    assert "12*****89" in text


def test_database_control_smoke_write_requires_explicit_flag(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(database_control_smoke, "app", smoke_app(calls))

    report = asyncio.run(
        database_control_smoke.run_database_control_smoke(
            actor_platform="qq",
            actor_user_id="123456789",
            allow_write=True,
            output_root=tmp_path,
        )
    )

    assert "POST relationship profile-admin" in calls
    assert "Mode: read-write" in report.read_text(encoding="utf-8")
