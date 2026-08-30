from __future__ import annotations

import time

from app.camera.contracts import CameraDemoScenario
from app.camera.demo_runtime import DemoCaptureController


def test_demo_capture_emits_structured_observations_without_a_frame_source() -> None:
    observations = []
    controller = DemoCaptureController(
        observation_callback=observations.append,
        interval_seconds=0.2,
    )
    job = controller.start(
        session_id="cam_" + "d" * 32,
        scenario=CameraDemoScenario.DESK_WORK,
    )
    deadline = time.monotonic() + 2
    while len(observations) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    controller.stop(job.session_id)

    assert len(observations) >= 2
    assert observations[0].scene_label == "desk"
    assert observations[0].objects == ("desk", "laptop", "keyboard", "book")
    assert observations[0].confidence == 0.98
    assert controller.status(job.session_id)["mode"] == "demo"
