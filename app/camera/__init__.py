"""Consent-gated local camera perception contracts.

This package never opens hardware or persists raw imagery. Hardware adapters and
vision models must submit only normalized observations through this boundary.
"""

from app.camera.contracts import CameraObservation, CameraSession, CameraSessionStatus
from app.camera.normalization import camera_observation_to_world_observation
from app.camera.session_manager import CameraSessionManager

__all__ = [
    "CameraObservation",
    "CameraSession",
    "CameraSessionManager",
    "CameraSessionStatus",
    "camera_observation_to_world_observation",
]
