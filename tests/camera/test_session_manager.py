from datetime import UTC, datetime, timedelta

import pytest

from app.camera.contracts import CameraObservation, CameraSessionStartRequest, CameraSessionStatus
from app.camera.session_manager import CameraSessionManager


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 23, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def test_disabled_camera_cannot_create_a_session() -> None:
    manager = CameraSessionManager(
        perception_enabled=False,
        local_capture_enabled=False,
        max_session_seconds=60,
    )
    with pytest.raises(PermissionError, match="disabled"):
        manager.start(CameraSessionStartRequest(consent_granted=True), owner_key="owner")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("raw_frame_retention_seconds", 1, "raw frame retention"),
        ("face_identification_enabled", True, "face identification"),
        ("cloud_upload_enabled", True, "cloud upload"),
    ),
)
def test_camera_manager_rejects_disallowed_privacy_modes(
    field: str, value: object, message: str
) -> None:
    options: dict[str, object] = {
        "perception_enabled": True,
        "local_capture_enabled": True,
        "max_session_seconds": 60,
    }
    options[field] = value
    with pytest.raises(ValueError, match=message):
        CameraSessionManager(**options)  # type: ignore[arg-type]


def test_session_expires_and_stop_is_terminal() -> None:
    clock = Clock()
    manager = CameraSessionManager(
        perception_enabled=True,
        local_capture_enabled=True,
        max_session_seconds=60,
        now=clock,
    )
    session = manager.start(CameraSessionStartRequest(consent_granted=True), owner_key="owner")
    assert session.status == CameraSessionStatus.ACTIVE
    stopped = manager.stop(session.session_id, owner_key="owner")
    assert stopped is not None and stopped.status == CameraSessionStatus.STOPPED
    assert manager.get(session.session_id, owner_key="owner").status == CameraSessionStatus.STOPPED

    another = manager.start(CameraSessionStartRequest(consent_granted=True), owner_key="owner")
    clock.now += timedelta(seconds=61)
    assert manager.get(another.session_id, owner_key="owner").status == CameraSessionStatus.EXPIRED
    assert manager.get(another.session_id, owner_key="other") is None


def test_capture_guard_marks_an_expired_session_inactive() -> None:
    clock = Clock()
    manager = CameraSessionManager(
        perception_enabled=True,
        local_capture_enabled=True,
        max_session_seconds=60,
        now=clock,
    )
    session = manager.start(CameraSessionStartRequest(consent_granted=True), owner_key="owner")

    assert manager.is_active_for_capture(session.session_id) is True
    clock.now += timedelta(seconds=61)
    assert manager.is_active_for_capture(session.session_id) is False


def test_only_active_high_confidence_observations_are_accepted() -> None:
    clock = Clock()
    manager = CameraSessionManager(
        perception_enabled=True, local_capture_enabled=True, max_session_seconds=60, now=clock
    )
    session = manager.start(CameraSessionStartRequest(consent_granted=True), owner_key="owner")
    observation = CameraObservation(
        session_id=session.session_id, objects=("book",), confidence=0.9, observed_at=clock.now
    )
    assert manager.validate_observation(observation, owner_key="owner") == session
    with pytest.raises(ValueError, match="confidence"):
        manager.validate_observation(
            observation.model_copy(update={"confidence": 0.5}), owner_key="owner"
        )
    manager.stop(session.session_id, owner_key="owner")
    with pytest.raises(PermissionError, match="not active"):
        manager.validate_observation(observation, owner_key="owner")
