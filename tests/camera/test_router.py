import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import httpx

from app.camera.router import create_camera_control_router
from app.core.config import load_settings
from fastapi import FastAPI


def test_camera_control_router_is_admin_gated_and_disabled_by_default(monkeypatch) -> None:
    class Actor:
        profile_id = "admin"

        class source_account:
            platform = "qq"

    async def authorize(*_args, **_kwargs):
        return Actor()

    async def audit(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.control.routes.require_control_admin", authorize)
    monkeypatch.setattr("app.control.routes.audit_control_result", audit)
    app = FastAPI()
    app.include_router(
        create_camera_control_router(
            replace(
                load_settings(),
                camera_perception_enabled=False,
                camera_local_capture_enabled=False,
            )
        )
    )

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.post(
                "/api/control/camera/sessions", json={"consent_granted": True}
            )

    response = asyncio.run(request())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "camera_disabled"


def test_camera_control_router_creates_and_stops_a_consented_session(monkeypatch) -> None:
    class Actor:
        profile_id = "admin"

        class source_account:
            platform = "qq"

    async def authorize(*_args, **_kwargs):
        return Actor()

    async def audit(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.control.routes.require_control_admin", authorize)
    monkeypatch.setattr("app.control.routes.audit_control_result", audit)
    app = FastAPI()
    settings = replace(
        load_settings(), camera_perception_enabled=True, camera_local_capture_enabled=True
    )
    app.include_router(create_camera_control_router(settings))

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            created = await client.post(
                "/api/control/camera/sessions", json={"consent_granted": True}
            )
            stopped = await client.post(
                f"/api/control/camera/sessions/{created.json()['session_id']}/stop"
            )
            return created, stopped

    created, stopped = asyncio.run(scenario())
    assert created.status_code == 200
    assert created.json()["status"] == "active"
    assert stopped.json()["status"] == "stopped"


def test_camera_control_router_accepts_only_a_live_high_confidence_observation(monkeypatch) -> None:
    class Actor:
        profile_id = "admin"

        class source_account:
            platform = "qq"

    async def authorize(*_args, **_kwargs):
        return Actor()

    async def audit(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.control.routes.require_control_admin", authorize)
    monkeypatch.setattr("app.control.routes.audit_control_result", audit)
    app = FastAPI()
    app.include_router(
        create_camera_control_router(
            replace(load_settings(), camera_perception_enabled=True, camera_local_capture_enabled=True)
        )
    )

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            created = await client.post("/api/control/camera/sessions", json={"consent_granted": True})
            session_id = created.json()["session_id"]
            accepted = await client.post(
                f"/api/control/camera/sessions/{session_id}/observations",
                json={"session_id": session_id, "objects": ["book"], "confidence": 0.9, "observed_at": datetime.now(UTC).isoformat()},
            )
            rejected = await client.post(
                f"/api/control/camera/sessions/{session_id}/observations",
                json={"session_id": session_id, "objects": ["book"], "confidence": 0.5, "observed_at": datetime.now(UTC).isoformat()},
            )
            return accepted, rejected

    accepted, rejected = asyncio.run(scenario())
    assert accepted.status_code == 200
    assert accepted.json()["capability"] == "vision_event"
    assert accepted.json()["sensitivity"] == "private"
    assert rejected.status_code == 409


def test_camera_perception_status_returns_only_stable_labels(monkeypatch) -> None:
    class Actor:
        profile_id = "admin"

        class source_account:
            platform = "qq"

    async def authorize(*_args, **_kwargs):
        return Actor()

    async def audit(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.control.routes.require_control_admin", authorize)
    monkeypatch.setattr("app.control.routes.audit_control_result", audit)
    app = FastAPI()
    app.include_router(create_camera_control_router(replace(load_settings(), camera_perception_enabled=True, camera_local_capture_enabled=True)))

    async def scenario() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            created = await client.post("/api/control/camera/sessions", json={"consent_granted": True})
            session_id = created.json()["session_id"]
            payload = {"session_id": session_id, "objects": ["book"], "pose_labels": ["sitting"], "confidence": 0.9, "observed_at": datetime.now(UTC).isoformat()}
            await client.post(f"/api/control/camera/sessions/{session_id}/observations", json=payload)
            await client.post(f"/api/control/camera/sessions/{session_id}/observations", json=payload)
            return await client.get(f"/api/control/camera/sessions/{session_id}/perception/status")

    response = asyncio.run(scenario())
    assert response.json()["available"] is True
    assert response.json()["objects"] == ["book"]
    assert response.json()["pose_labels"] == ["sitting"]
    assert "session_id" not in response.json()
