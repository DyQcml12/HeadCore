import httpx

from scripts.camera_control import CameraControlClient, parse_args, run


def test_camera_control_builds_admin_headers_and_start_request(monkeypatch) -> None:
    captured = {}

    def request(method, url, *, headers, json, timeout):
        captured.update(method=method, url=url, headers=headers, json=json, timeout=timeout)
        return httpx.Response(200, json={"session_id": "cam_123"}, request=httpx.Request(method, url))

    monkeypatch.setattr("scripts.camera_control.httpx.request", request)
    args = parse_args(["--actor-user-id", "10001", "session-start", "--camera-slot", "2"])

    result = run(args)

    assert result == {"session_id": "cam_123"}
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:8000/api/control/camera/sessions"
    assert captured["headers"]["X-Hutao-Actor-User-Id"] == "10001"
    assert captured["json"] == {"consent_granted": True, "camera_slot": 2}


def test_camera_control_builds_local_camera_capture_request(monkeypatch) -> None:
    captured = {}

    def request(method, url, *, headers, json, timeout):
        captured.update(method=method, url=url, json=json)
        return httpx.Response(200, json={"started": True}, request=httpx.Request(method, url))

    monkeypatch.setattr("scripts.camera_control.httpx.request", request)
    args = parse_args(["--actor-user-id", "10001", "camera-capture-start", "--session-id", "cam_123"])

    assert run(args) == {"started": True}
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/control/camera/sessions/cam_123/capture/start")
    assert captured["json"] is None


def test_camera_control_redacts_rejected_response_details(monkeypatch) -> None:
    def request(method, url, *, headers, json, timeout):
        response = httpx.Response(403, json={"detail": {"code": "admin_required"}}, request=httpx.Request(method, url))
        response.raise_for_status()
        return response

    monkeypatch.setattr("scripts.camera_control.httpx.request", request)
    args = parse_args(["--actor-user-id", "10001", "capture-status", "--session-id", "cam_123"])

    try:
        run(args)
    except RuntimeError as exc:
        assert str(exc) == "control_request_rejected:403:admin_required"
    else:
        raise AssertionError("expected rejected request")


def test_camera_control_identifies_unreachable_core(monkeypatch) -> None:
    def request(method, url, *, headers, json, timeout):
        raise httpx.ConnectError("connection refused", request=httpx.Request(method, url))

    monkeypatch.setattr("scripts.camera_control.httpx.request", request)
    args = parse_args(["--actor-user-id", "10001", "session-start"])

    try:
        run(args)
    except RuntimeError as exc:
        assert str(exc) == "control_core_unreachable:http://127.0.0.1:8000"
    else:
        raise AssertionError("expected unreachable core")
