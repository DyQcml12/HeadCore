from __future__ import annotations

import pytest

from app.camera.browser_runtime import BrowserFrameProcessor
from app.camera.local_runtime import CameraAnalysis


class FakeAnalyzer:
    def __init__(self) -> None:
        self.closed = False
        self.frames: list[object] = []

    def analyze(self, frame: object) -> CameraAnalysis:
        self.frames.append(frame)
        return CameraAnalysis(
            scene_label="desk",
            objects=("book",),
            confidence=0.72,
        )

    def close(self) -> None:
        self.closed = True


def test_browser_processor_analyzes_a_frame_and_emits_only_structured_observation(monkeypatch) -> None:
    decoded_frame = object()
    monkeypatch.setattr("app.camera.browser_runtime._decode_image", lambda _payload: decoded_frame)
    analyzers: list[FakeAnalyzer] = []
    observations = []
    processor = BrowserFrameProcessor(
        analyzer_factory=lambda: analyzers.append(FakeAnalyzer()) or analyzers[-1],
        observation_callback=observations.append,
        session_active=lambda _session_id: True,
    )

    job = processor.start(session_id="cam_" + "b" * 32)
    result = processor.process(session_id=job.session_id, payload=b"jpeg-bytes")

    assert result == {
        "accepted": True,
        "observation_emitted": True,
        "frames_received": 1,
        "observations_emitted": 1,
    }
    assert analyzers[0].frames == [decoded_frame]
    assert len(observations) == 1
    assert observations[0].scene_label == "desk"
    assert observations[0].objects == ("book",)
    assert "frame" not in vars(job)
    assert processor.status(job.session_id)["last_frame_at"] is not None


def test_browser_processor_stop_closes_analyzer_and_rejects_later_frames(monkeypatch) -> None:
    monkeypatch.setattr("app.camera.browser_runtime._decode_image", lambda _payload: object())
    analyzers: list[FakeAnalyzer] = []
    processor = BrowserFrameProcessor(
        analyzer_factory=lambda: analyzers.append(FakeAnalyzer()) or analyzers[-1],
        observation_callback=lambda _observation: None,
        session_active=lambda _session_id: True,
    )
    session_id = "cam_" + "c" * 32
    processor.start(session_id=session_id)

    stopped = processor.stop(session_id)

    assert stopped is not None
    assert analyzers[0].closed is True
    assert processor.status(session_id)["state"] == "stopped"
    with pytest.raises(LookupError, match="camera_capture_not_started"):
        processor.process(session_id=session_id, payload=b"jpeg-bytes")


def test_browser_processor_rejects_inactive_sessions_before_decoding(monkeypatch) -> None:
    decoded = False

    def decode(_payload: bytes):
        nonlocal decoded
        decoded = True
        return object()

    monkeypatch.setattr("app.camera.browser_runtime._decode_image", decode)
    processor = BrowserFrameProcessor(
        analyzer_factory=FakeAnalyzer,
        observation_callback=lambda _observation: None,
        session_active=lambda _session_id: False,
    )
    session_id = "cam_" + "d" * 32
    processor.start(session_id=session_id)

    with pytest.raises(PermissionError, match="camera_session_not_active"):
        processor.process(session_id=session_id, payload=b"jpeg-bytes")

    assert decoded is False
    assert processor.status(session_id)["state"] == "stopped"
