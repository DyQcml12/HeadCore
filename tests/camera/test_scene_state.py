from __future__ import annotations

from datetime import UTC, datetime

from app.camera.contracts import CameraObservation
from app.camera.scene_state import derive_scene_state


def observation(**overrides: object) -> CameraObservation:
    values: dict[str, object] = {
        "session_id": "camera-session-0000000000000000",
        "scene_label": "desk",
        "objects": ("keyboard", "laptop"),
        "pose_labels": ("sitting",),
        "gesture_labels": ("typing",),
        "confidence": 0.91,
        "observed_at": datetime.now(UTC),
    }
    values.update(overrides)
    return CameraObservation(**values)


def test_scene_state_derives_desk_work_from_direct_labels() -> None:
    state = derive_scene_state(observation())

    assert state.state_id == "desk_work"
    assert state.facts == ("desk_scene", "activity:typing")
    assert state.confidence == 0.91


def test_scene_state_derives_street_vehicle_without_identity_or_intent() -> None:
    state = derive_scene_state(
        observation(scene_label="street", objects=("car",), pose_labels=(), gesture_labels=())
    )

    assert state.state_id == "street_vehicle"
    assert state.facts == ("street_scene",)
    assert "emotion" not in str(state.as_dict())
    assert "identity" not in str(state.as_dict())
    assert "intent" not in str(state.as_dict())


def test_scene_state_fails_closed_when_no_scene_labels_are_available() -> None:
    state = derive_scene_state(
        observation(scene_label="", objects=(), pose_labels=(), gesture_labels=())
    )

    assert state.state_id == "unclassified"
    assert state.reason_codes == ("insufficient_allowlisted_labels",)
