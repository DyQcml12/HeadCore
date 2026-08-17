from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.camera.contracts import CameraObservation
from app.camera.evidence_store import CameraEvidenceStore
from app.camera.temporal_state import CameraTemporalUpdate


def observation(**overrides: object) -> CameraObservation:
    values = {
        "session_id": "camera-session-0000000000000000",
        "scene_label": "desk",
        "objects": ("keyboard", "laptop"),
        "pose_labels": ("sitting",),
        "gesture_labels": ("typing",),
        "facial_cues": ("head_down_detected",),
        "confidence": 0.9,
        "observed_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return CameraObservation(**values)


def test_store_renders_confirmed_labels_and_changes() -> None:
    store = CameraEvidenceStore(max_age_seconds=300)
    store.record_update(CameraTemporalUpdate(observation(), changes=("appeared: person",)))

    context = store.latest_context()

    assert "scene: desk" in context
    assert "objects: keyboard, laptop" in context
    assert "pose: sitting" in context
    assert "gesture: typing" in context
    assert "appeared: person" in context


def test_store_is_empty_without_updates() -> None:
    store = CameraEvidenceStore()
    assert store.latest_context() == ""


def test_store_removes_session_context_on_stop() -> None:
    store = CameraEvidenceStore()
    store.record_update(CameraTemporalUpdate(observation()))
    store.remove_session("camera-session-0000000000000000")
    assert store.latest_context() == ""


def test_store_prunes_stale_context() -> None:
    store = CameraEvidenceStore(max_age_seconds=300)
    stale = observation(
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    store.record_update(CameraTemporalUpdate(stale))

    assert store.latest_context() == ""


def test_store_rejects_invalid_max_age() -> None:
    import pytest

    with pytest.raises(ValueError, match="max_age_seconds"):
        CameraEvidenceStore(max_age_seconds=0)
