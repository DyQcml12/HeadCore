from datetime import UTC, datetime

import pytest

from app.camera.contracts import CameraObservation
from app.camera.normalization import camera_observation_to_world_observation
from app.world.contracts import DataSensitivity, WorldSourceCapability


def test_camera_event_becomes_short_lived_private_world_observation() -> None:
    now = datetime(2026, 7, 23, tzinfo=UTC)
    observation = CameraObservation(
        session_id="cam_" + "a" * 32,
        scene_label="desk",
        objects=("book", "cup"),
        pose_labels=("sitting",),
        confidence=0.9,
        observed_at=now,
    )

    world = camera_observation_to_world_observation(observation, ttl_seconds=15)

    assert world.capability == WorldSourceCapability.VISION_EVENT
    assert world.sensitivity == DataSensitivity.PRIVATE
    assert world.expires_at.timestamp() - world.observed_at.timestamp() == 15
    assert world.evidence[0].source_uri == "local://camera/structured-observation"
    assert observation.session_id not in repr(world)
    assert len(world.evidence[0].content_hash) == 64


def test_camera_event_ttl_is_bounded() -> None:
    observation = CameraObservation(
        session_id="cam_" + "a" * 32,
        confidence=0.9,
        observed_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="ttl_seconds"):
        camera_observation_to_world_observation(observation, ttl_seconds=0)
