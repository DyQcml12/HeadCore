import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import shutil
import socket
import subprocess
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from app.camera.router import build_camera_control_runtime
from app.camera.local_runtime import CameraAnalysis
from app.core.config import load_settings
from app.workbench.router import create_visual_workbench_router
from app.workbench.sessions import (
    WorkbenchAuthenticationError,
    WorkbenchRateLimitError,
    WorkbenchSessionStore,
)


def _playwright_available(node: str) -> bool:
    try:
        probe = subprocess.run(
            [node, "-e", "require('playwright')"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return probe.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _start_local_server(app: FastAPI, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("local FastAPI server did not start for visual workbench browser test")
    return server, thread


class _FakeBrowserAnalyzer:
    def analyze(self, _frame: object) -> CameraAnalysis:
        return CameraAnalysis(scene_label="desk", objects=("book",), confidence=0.92)

    def close(self) -> None:
        return None


def test_visual_workbench_requires_a_local_admin_session_for_bounded_consented_camera_sessions() -> None:
    settings = replace(
        load_settings(),
        visual_workbench_enabled=True,
        visual_workbench_admin_secret="test-local-admin-secret",
        visual_workbench_session_lifetime_seconds=900,
        camera_perception_enabled=True,
        camera_local_capture_enabled=True,
        camera_session_max_seconds=90,
    )
    app = FastAPI()
    camera_runtime = build_camera_control_runtime(settings)
    camera_runtime.capabilities.update({"capture_ready": True, "labeling_ready": True, "reason_codes": []})
    app.include_router(create_visual_workbench_router(settings, camera_runtime))

    async def scenario() -> tuple[
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
    ]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            anonymous = await client.get("/api/workbench/status")
            rejected_login = await client.post(
                "/api/workbench/login", json={"secret": "wrong-secret"}
            )
            accepted_login = await client.post(
                "/api/workbench/login", json={"secret": "test-local-admin-secret"}
            )
            missing_csrf = await client.post(
                "/api/workbench/camera/sessions", json={"consent_granted": True}
            )
            csrf_token = client.cookies.get("hutao_workbench_csrf")
            assert csrf_token
            rejected_consent = await client.post(
                "/api/workbench/camera/sessions",
                headers={"X-CSRF-Token": csrf_token},
                json={"consent_granted": False},
            )
            created = await client.post(
                "/api/workbench/camera/sessions",
                headers={"X-CSRF-Token": csrf_token},
                json={"consent_granted": True, "camera_slot": 0},
            )
            return anonymous, rejected_login, accepted_login, missing_csrf, rejected_consent, created

    anonymous, rejected_login, accepted_login, missing_csrf, rejected_consent, created = asyncio.run(scenario())

    assert anonymous.status_code == 401
    assert rejected_login.status_code == 401
    assert accepted_login.status_code == 204
    assert "HttpOnly" in accepted_login.headers["set-cookie"]
    assert missing_csrf.status_code == 403
    assert rejected_consent.status_code == 422
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "active"
    created_at = datetime.fromisoformat(body["created_at"])
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert (expires_at - created_at).total_seconds() == 90


def test_visual_workbench_shell_is_separate_from_the_control_api() -> None:
    settings = replace(
        load_settings(),
        visual_workbench_enabled=True,
        visual_workbench_admin_secret="test-local-admin-secret",
    )
    app = FastAPI()
    app.include_router(
        create_visual_workbench_router(settings, build_camera_control_runtime(settings))
    )

    async def request() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get("/workbench"), await client.get("/workbench/app.js")

    page, script = asyncio.run(request())

    assert page.status_code == 200
    assert script.status_code == 200
    assert "/ui/liquid-theme.css" in page.text
    assert "HutaoChatCore" in page.text
    assert 'id="localPreview"' in page.text
    assert 'id="recognitionResult"' in page.text
    assert 'id="frameCount"' in page.text
    assert 'id="sceneLabels"' in page.text
    assert 'id="visualSummary"' in page.text
    assert 'id="changeLabels"' in page.text
    assert "画面只发送到 127.0.0.1 分析，单帧处理后立即释放，不上传或保存" in page.text
    assert 'id="visionDiagnostics"' in page.text
    assert "getUserMedia" in script.text
    assert "renderLabelGroup" in script.text
    assert "summarizeObservation" in script.text
    assert "visualLabelNames" in script.text
    assert "observationCount" in script.text
    assert "captureStartErrorMessage" in script.text
    assert "127.0.0.1:8000 正在运行" in script.text
    assert "管理员会话已失效，请重新登录" in script.text
    assert "beforeunload" in script.text
    assert "camera_device_unavailable" in script.text
    assert "真实采集未启用" in script.text
    assert "真实识别未启用" in script.text
    assert "VISUAL_WORKBENCH_ENABLED=true" in script.text
    assert "for (const control of $(\"#loginForm\").elements) control.disabled = false" in script.text
    assert "/api/workbench/" in script.text
    assert "/api/control/" not in page.text
    assert "/api/control/" not in script.text


def test_visual_workbench_status_exposes_capture_and_labeling_diagnostics() -> None:
    settings = replace(
        load_settings(),
        visual_workbench_enabled=True,
        visual_workbench_admin_secret="test-local-admin-secret",
        camera_perception_enabled=True,
        camera_local_capture_enabled=True,
        camera_mediapipe_enabled=False,
        camera_yolo_model_path="D:/does-not-exist/yolo.pt",
    )
    app = FastAPI()
    app.include_router(
        create_visual_workbench_router(settings, build_camera_control_runtime(settings))
    )

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            login = await client.post(
                "/api/workbench/login", json={"secret": "test-local-admin-secret"}
            )
            assert login.status_code == 204
            return await client.get("/api/workbench/status")

    response = asyncio.run(request())

    assert response.status_code == 200
    camera = response.json()["camera"]
    assert camera["available"] is True
    assert "capture_ready" in camera
    assert camera["labeling_ready"] is False
    assert "yolo_model_missing" in camera["diagnostics"]["reason_codes"]


def test_visual_workbench_demo_session_uses_the_structured_observation_chain() -> None:
    settings = replace(
        load_settings(),
        visual_workbench_enabled=True,
        visual_workbench_admin_secret="test-local-admin-secret",
        camera_perception_enabled=False,
        camera_local_capture_enabled=False,
        camera_demo_enabled=True,
        camera_capture_interval_seconds=0.2,
    )
    app = FastAPI()
    camera_runtime = build_camera_control_runtime(settings)
    app.include_router(create_visual_workbench_router(settings, camera_runtime))

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            login = await client.post(
                "/api/workbench/login", json={"secret": "test-local-admin-secret"}
            )
            assert login.status_code == 204
            csrf_token = client.cookies.get("hutao_workbench_csrf")
            assert csrf_token
            status_response = await client.get("/api/workbench/status")
            created = await client.post(
                "/api/workbench/camera/demo/sessions",
                headers={"X-CSRF-Token": csrf_token},
                json={"scenario": "desk_work"},
            )
            started = await client.post(
                f"/api/workbench/camera/sessions/{created.json()['session_id']}/capture/start",
                headers={"X-CSRF-Token": csrf_token},
            )
            time.sleep(0.35)
            perception = await client.get(
                f"/api/workbench/camera/sessions/{created.json()['session_id']}/perception/status"
            )
            context = await client.get("/api/v1/visual/context")
            return status_response, created, started, perception, context

    status_response, created, started, perception, context = asyncio.run(scenario())

    assert status_response.status_code == 200
    camera_status = status_response.json()["camera"]
    assert camera_status["available"] is True
    assert camera_status["real_available"] is False
    assert camera_status["demo_available"] is True
    assert created.status_code == 200
    assert created.json()["mode"] == "demo"
    assert created.json()["demo_scenario"] == "desk_work"
    assert started.status_code == 200
    assert started.json()["mode"] == "demo"
    assert perception.status_code == 200
    body = perception.json()
    assert body["available"] is True
    assert body["mode"] == "demo"
    assert body["scene_state"] == "desk_work"
    assert context.status_code == 200
    context_body = context.json()
    assert context_body["available"] is True
    assert context_body["scene_state"] == "desk_work"
    assert "desk_scene" in context_body["scene_facts"]
    assert context_body["objects"]


def test_visual_workbench_capture_is_csrf_protected_and_bound_to_its_admin_session(monkeypatch) -> None:
    settings = replace(
        load_settings(),
        visual_workbench_enabled=True,
        visual_workbench_admin_secret="test-local-admin-secret",
        camera_perception_enabled=True,
        camera_local_capture_enabled=True,
    )
    app = FastAPI()
    camera_runtime = build_camera_control_runtime(settings)
    camera_runtime.capabilities.update({"capture_ready": True, "labeling_ready": True, "reason_codes": []})
    monkeypatch.setattr(camera_runtime.capture, "start", lambda **_kwargs: object())
    app.include_router(create_visual_workbench_router(settings, camera_runtime))

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as owner:
            login = await owner.post("/api/workbench/login", json={"secret": "test-local-admin-secret"})
            assert login.status_code == 204
            csrf_token = owner.cookies.get("hutao_workbench_csrf")
            assert csrf_token
            created = await owner.post(
                "/api/workbench/camera/sessions",
                headers={"X-CSRF-Token": csrf_token},
                json={"consent_granted": True},
            )
            session_id = created.json()["session_id"]
            csrf_rejected = await owner.post(
                f"/api/workbench/camera/sessions/{session_id}/capture/start"
            )
            started = await owner.post(
                f"/api/workbench/camera/sessions/{session_id}/capture/start",
                headers={"X-CSRF-Token": csrf_token},
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as other_admin:
                other_login = await other_admin.post(
                    "/api/workbench/login", json={"secret": "test-local-admin-secret"}
                )
                assert other_login.status_code == 204
                hidden = await other_admin.get(
                    f"/api/workbench/camera/sessions/{session_id}/capture/status"
                )
            return created, csrf_rejected, started, hidden

    created, csrf_rejected, started, hidden = asyncio.run(scenario())

    assert created.status_code == 200
    assert csrf_rejected.status_code == 403
    assert started.status_code == 200
    assert started.json()["started"] is True
    assert hidden.status_code == 404


def test_visual_workbench_browser_frames_reach_perception_and_stop_cleanly(monkeypatch) -> None:
    settings = replace(
        load_settings(),
        visual_workbench_enabled=True,
        visual_workbench_admin_secret="test-local-admin-secret",
        camera_perception_enabled=True,
        camera_local_capture_enabled=True,
    )
    app = FastAPI()
    camera_runtime = build_camera_control_runtime(settings)
    camera_runtime.capabilities.update({"capture_ready": True, "labeling_ready": True, "reason_codes": []})
    camera_runtime.browser._analyzer_factory = _FakeBrowserAnalyzer
    monkeypatch.setattr("app.camera.browser_runtime._decode_image", lambda _payload: object())
    app.include_router(create_visual_workbench_router(settings, camera_runtime))

    async def scenario() -> tuple[
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
    ]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            login = await client.post("/api/workbench/login", json={"secret": "test-local-admin-secret"})
            assert login.status_code == 204
            csrf_token = client.cookies.get("hutao_workbench_csrf")
            assert csrf_token
            created = await client.post(
                "/api/workbench/camera/sessions",
                headers={"X-CSRF-Token": csrf_token},
                json={"consent_granted": True},
            )
            session_id = created.json()["session_id"]
            started = await client.post(
                f"/api/workbench/camera/sessions/{session_id}/capture/start",
                headers={"X-CSRF-Token": csrf_token},
            )
            frame = await client.post(
                f"/api/workbench/camera/sessions/{session_id}/frames",
                headers={"X-CSRF-Token": csrf_token},
                files={"frame": ("camera.jpg", b"jpeg-bytes", "image/jpeg")},
            )
            confirmed_frame = await client.post(
                f"/api/workbench/camera/sessions/{session_id}/frames",
                headers={"X-CSRF-Token": csrf_token},
                files={"frame": ("camera.jpg", b"jpeg-bytes", "image/jpeg")},
            )
            perception = await client.get(
                f"/api/workbench/camera/sessions/{session_id}/perception/status"
            )
            stopped = await client.post(
                f"/api/workbench/camera/sessions/{session_id}/capture/stop",
                headers={"X-CSRF-Token": csrf_token},
            )
            after_stop = await client.post(
                f"/api/workbench/camera/sessions/{session_id}/frames",
                headers={"X-CSRF-Token": csrf_token},
                files={"frame": ("camera.jpg", b"jpeg-bytes", "image/jpeg")},
            )
            return started, frame, confirmed_frame, perception, stopped, after_stop

    started, frame, confirmed_frame, perception, stopped, after_stop = asyncio.run(scenario())

    assert started.status_code == 200
    assert started.json()["mode"] == "browser"
    assert frame.status_code == 200
    assert frame.json()["observation_emitted"] is True
    assert frame.json()["frames_received"] == 1
    assert confirmed_frame.status_code == 200
    assert confirmed_frame.json()["observation_emitted"] is True
    assert confirmed_frame.json()["frames_received"] == 2
    assert perception.status_code == 200
    assert perception.json()["available"] is True
    assert perception.json()["objects"] == ["book"]
    assert stopped.status_code == 200
    assert stopped.json()["was_running"] is True
    assert after_stop.status_code == 409
    assert after_stop.json()["detail"]["code"] == "camera_capture_not_started"


def test_visual_workbench_blocks_repeated_invalid_local_admin_secrets() -> None:
    store = WorkbenchSessionStore(
        enabled=True,
        admin_secret="test-local-admin-secret",
        lifetime_seconds=900,
    )
    timestamp = datetime(2026, 7, 30, tzinfo=UTC)

    for _ in range(5):
        try:
            store.login(supplied_secret="wrong-secret", subject="127.0.0.1", now=timestamp)
        except WorkbenchAuthenticationError:
            pass
        else:
            raise AssertionError("invalid administrator secret must be rejected")

    try:
        store.login(supplied_secret="test-local-admin-secret", subject="127.0.0.1", now=timestamp)
    except WorkbenchRateLimitError:
        pass
    else:
        raise AssertionError("valid administrator secret must stay blocked during the cooldown")

    accepted = store.login(
        supplied_secret="test-local-admin-secret",
        subject="127.0.0.1",
        now=timestamp + timedelta(minutes=16),
    )
    assert accepted.identity.session_id.startswith("wb_")


def test_visual_workbench_allows_only_one_active_camera_session_per_admin() -> None:
    settings = replace(
        load_settings(),
        visual_workbench_enabled=True,
        visual_workbench_admin_secret="test-local-admin-secret",
        camera_perception_enabled=True,
        camera_local_capture_enabled=True,
    )
    app = FastAPI()
    camera_runtime = build_camera_control_runtime(settings)
    camera_runtime.capabilities.update({"capture_ready": True, "labeling_ready": True, "reason_codes": []})
    app.include_router(create_visual_workbench_router(settings, camera_runtime))

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            login = await client.post("/api/workbench/login", json={"secret": "test-local-admin-secret"})
            assert login.status_code == 204
            csrf_token = client.cookies.get("hutao_workbench_csrf")
            assert csrf_token
            first = await client.post(
                "/api/workbench/camera/sessions",
                headers={"X-CSRF-Token": csrf_token},
                json={"consent_granted": True},
            )
            second = await client.post(
                "/api/workbench/camera/sessions",
                headers={"X-CSRF-Token": csrf_token},
                json={"consent_granted": True},
            )
            return first, second

    first, second = asyncio.run(scenario())

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "camera_session_already_active"


def test_visual_workbench_explains_unavailable_configuration_without_disabling_input() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the workbench browser test")
    if not _playwright_available(node):
        pytest.skip("playwright is not installed; workbench browser test requires playwright + Microsoft Edge")
    settings = replace(load_settings(), visual_workbench_enabled=False)
    app = FastAPI()
    app.include_router(
        create_visual_workbench_router(settings, build_camera_control_runtime(settings))
    )
    port = _unused_local_port()
    server, thread = _start_local_server(app, port)
    browser_script = r'''
const { chromium } = require('playwright');
const baseUrl = process.argv[1];
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(`${baseUrl}/workbench`, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => document.querySelector('#gateNote').dataset.state === 'unavailable');
    if (await page.locator('#adminSecret').isDisabled()) throw new Error('unavailable workbench disabled the secret field');
    if (!await page.locator('#gateNote').textContent().then((text) => text.includes('VISUAL_WORKBENCH_ENABLED=true'))) throw new Error('missing configuration guidance');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error.stack || error); process.exit(1); });
'''
    try:
        completed = subprocess.run(
            [node, "-e", browser_script, f"http://127.0.0.1:{port}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    assert completed.returncode == 0, completed.stderr or completed.stdout
