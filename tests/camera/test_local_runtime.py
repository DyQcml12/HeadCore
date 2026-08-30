from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace

from app.camera.local_runtime import (
    CameraAnalysis,
    LocalCaptureController,
    LocalVisionAnalyzer,
    _is_pointing_hand,
    _is_raised_hand,
    _infer_scene_label,
    inspect_local_vision_capabilities,
)


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
        return CameraAnalysis(objects=("book",), confidence=0.72)

    def close(self) -> None:
        self.closed = True


def test_capture_controller_reports_a_bounded_failure_reason() -> None:
    def unavailable_source(_slot: int):
        raise RuntimeError("camera device is unavailable")

    controller = LocalCaptureController(
        source_factory=unavailable_source,
        analyzer_factory=FakeAnalyzer,
        observation_callback=lambda _observation: None,
        minimum_interval_seconds=0.2,
    )
    job = controller.start(session_id="cam_" + "e" * 32, camera_slot=0)
    deadline = time.monotonic() + 2
    while controller.status(job.session_id)["running"] and time.monotonic() < deadline:
        time.sleep(0.02)

    status = controller.status(job.session_id)
    assert status["state"] == "failed"
    assert status["reason_code"] == "camera_device_unavailable"
    assert status["last_error"] == "camera_device_unavailable"


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


def test_local_analyzer_maps_common_yolo_names_to_contract_labels() -> None:
    class FakeTensor:
        def __init__(self, values):
            self._values = values

        def tolist(self):
            return self._values

    class FakeModel:
        def predict(self, _frame, **_kwargs):
            return [SimpleNamespace(
                names={0: "cell phone", 1: "dining table", 2: "unknown"},
                boxes=SimpleNamespace(
                    cls=FakeTensor([0, 1, 2]),
                    conf=FakeTensor([0.91, 0.88, 0.99]),
                ),
            )]

    analyzer = LocalVisionAnalyzer(enable_mediapipe=False)
    analyzer._yolo = FakeModel()

    labels, scores = analyzer._detect_objects(object())

    assert labels == ("phone", "table")
    assert scores == [0.91, 0.88]


def test_hand_helpers_require_a_wrist_above_the_shoulder_and_a_single_extended_finger() -> None:
    folded = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    folded[0] = SimpleNamespace(x=0.0, y=0.2)
    folded[6] = SimpleNamespace(x=0.1, y=0.2)
    folded[8] = SimpleNamespace(x=0.11, y=0.2)
    folded[10] = SimpleNamespace(x=0.1, y=0.2)
    folded[12] = SimpleNamespace(x=0.11, y=0.2)
    folded[14] = SimpleNamespace(x=0.1, y=0.2)
    folded[16] = SimpleNamespace(x=0.11, y=0.2)
    folded[18] = SimpleNamespace(x=0.1, y=0.2)
    folded[20] = SimpleNamespace(x=0.11, y=0.2)

    assert _is_raised_hand(folded[0], 0.5) is True
    assert _is_raised_hand(SimpleNamespace(x=0.0, y=0.5), 0.5) is False
    assert _is_pointing_hand(folded) is False

    folded[8] = SimpleNamespace(x=0.45, y=0.2)
    assert _is_pointing_hand(folded) is True


def test_local_vision_capability_diagnostics_explain_missing_label_model() -> None:
    capability = inspect_local_vision_capabilities(
        yolo_model_path="D:/does-not-exist/yolo.pt",
        enable_mediapipe=False,
    )

    assert capability.yolo_model_configured is True
    assert capability.yolo_model_exists is False
    assert capability.labeling_ready is False
    assert "yolo_model_missing" in capability.reason_codes


def test_scene_label_is_derived_only_from_allowlisted_detected_objects() -> None:
    assert _infer_scene_label(("desk", "laptop")) == "desk"
    assert _infer_scene_label(("car",)) == "street"
    assert _infer_scene_label(("person",)) == ""
