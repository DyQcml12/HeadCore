from __future__ import annotations

import time
from datetime import UTC, datetime

from app.camera.local_runtime import CameraAnalysis, LocalCaptureController, LocalVisionAnalyzer


class FakeSource:
    def __init__(self) -> None:
        self.released = False
        self.calls = 0

    def read(self):
        self.calls += 1
        return True, object()

    def release(self) -> None:
        self.released = True


class FakeAnalyzer:
    def __init__(self) -> None:
        self.closed = False

    def analyze(self, _frame: object) -> CameraAnalysis:
        return CameraAnalysis(objects=("book",), confidence=0.9)

    def close(self) -> None:
        self.closed = True


def test_capture_controller_emits_transient_observations_and_releases_resources() -> None:
    source = FakeSource()
    analyzer = FakeAnalyzer()
    observations = []
    controller = LocalCaptureController(
        source_factory=lambda _slot: source,
        analyzer_factory=lambda: analyzer,
        observation_callback=observations.append,
        minimum_interval_seconds=0.2,
    )

    job = controller.start(session_id="cam_" + "a" * 32, camera_slot=0)
    deadline = time.monotonic() + 2
    while not observations and time.monotonic() < deadline:
        time.sleep(0.02)
    stopped = controller.stop(job.session_id)

    assert stopped is not None
    assert observations[0].objects == ("book",)
    assert observations[0].observed_at.tzinfo == UTC
    assert source.released is True
    assert analyzer.closed is True
    assert controller.status(job.session_id)["running"] is False


def test_capture_controller_can_use_an_explicit_non_camera_frame_source() -> None:
    selected_source = FakeSource()
    default_source_called = False
    observations = []

    def default_source(_slot: int) -> FakeSource:
        nonlocal default_source_called
        default_source_called = True
        return FakeSource()

    controller = LocalCaptureController(
        source_factory=default_source,
        analyzer_factory=FakeAnalyzer,
        observation_callback=observations.append,
        minimum_interval_seconds=0.2,
    )
    job = controller.start(
        session_id="cam_" + "b" * 32,
        camera_slot=0,
        source_factory=lambda _slot: selected_source,
    )
    deadline = time.monotonic() + 2
    while not observations and time.monotonic() < deadline:
        time.sleep(0.02)
    controller.stop(job.session_id)

    assert observations
    assert default_source_called is False
    assert selected_source.released is True


def test_capture_controller_stops_when_the_session_guard_is_no_longer_active() -> None:
    source = FakeSource()
    analyzer = FakeAnalyzer()
    controller = LocalCaptureController(
        source_factory=lambda _slot: source,
        analyzer_factory=lambda: analyzer,
        observation_callback=lambda _observation: None,
        session_active=lambda _session_id: False,
        minimum_interval_seconds=0.2,
    )

    job = controller.start(session_id="cam_" + "d" * 32, camera_slot=0)
    deadline = time.monotonic() + 2
    while controller.status(job.session_id)["running"] and time.monotonic() < deadline:
        time.sleep(0.02)

    status = controller.status(job.session_id)
    assert status["running"] is False
    assert status["last_error"] == "camera_session_not_active"
    assert source.released is True
    assert analyzer.closed is True


def test_local_analyzer_without_installed_local_models_emits_no_unverified_labels() -> None:
    analyzer = LocalVisionAnalyzer(enable_mediapipe=False)

    analysis = analyzer.analyze(object())

    assert analysis == CameraAnalysis()
