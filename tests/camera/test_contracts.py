from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.camera.contracts import CameraObservation, CameraSessionStartRequest


def test_camera_start_requires_explicit_consent() -> None:
    with pytest.raises(ValidationError, match="explicitly granted"):
        CameraSessionStartRequest(consent_granted=False)


def test_camera_observation_rejects_identity_raw_frame_and_emotion_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CameraObservation(
            session_id="cam_" + "a" * 32,
            confidence=0.9,
            observed_at=datetime.now(UTC),
            identity="someone",
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CameraObservation(
            session_id="cam_" + "a" * 32,
            confidence=0.9,
            observed_at=datetime.now(UTC),
            emotion="happy",
        )


def test_camera_observation_accepts_only_allowlisted_machine_labels() -> None:
    observation = CameraObservation(
        session_id="cam_" + "a" * 32,
        scene_label="desk",
        objects=("book", "cup"),
        pose_labels=("sitting",),
        gesture_labels=("typing",),
        facial_cues=("head_down_detected",),
        confidence=0.91,
        observed_at=datetime.now(UTC),
    )

    assert observation.facial_cues == ("head_down_detected",)
    with pytest.raises(ValidationError, match="non-allowlisted"):
        CameraObservation(
            session_id="cam_" + "a" * 32,
            objects=("wallet",),
            confidence=0.9,
            observed_at=datetime.now(UTC),
        )
