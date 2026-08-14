from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import uuid4

from app.camera.contracts import (
    CameraObservation,
    CameraSession,
    CameraSessionStartRequest,
    CameraSessionStatus,
)


class CameraSessionManager:
    """In-memory consent ledger only; never opens a camera or starts a worker."""

    def __init__(
        self,
        *,
        perception_enabled: bool,
        local_capture_enabled: bool,
        max_session_seconds: int,
        raw_frame_retention_seconds: int = 0,
        face_identification_enabled: bool = False,
        cloud_upload_enabled: bool = False,
        minimum_observation_confidence: float = 0.85,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not 30 <= max_session_seconds <= 3600:
            raise ValueError("camera max_session_seconds must be between 30 and 3600")
        if raw_frame_retention_seconds != 0:
            raise ValueError("camera raw frame retention is not supported")
        if face_identification_enabled:
            raise ValueError("camera face identification is not supported")
        if cloud_upload_enabled:
            raise ValueError("camera cloud upload is not supported")
        if not 0.0 <= minimum_observation_confidence <= 1.0:
            raise ValueError("camera minimum_observation_confidence must be between 0 and 1")
        self._perception_enabled = perception_enabled
        self._local_capture_enabled = local_capture_enabled
        self._max_session_seconds = max_session_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._sessions: dict[str, CameraSession] = {}
        self._owners: dict[str, str] = {}
        self._minimum_observation_confidence = minimum_observation_confidence

    def start(self, request: CameraSessionStartRequest, *, owner_key: str) -> CameraSession:
        if not self._perception_enabled or not self._local_capture_enabled:
            raise PermissionError("camera perception is disabled")
        if not owner_key.strip():
            raise ValueError("camera session owner is required")
        now = self._now()
        session = CameraSession(
            session_id=f"cam_{uuid4().hex}",
            camera_slot=request.camera_slot,
            status=CameraSessionStatus.ACTIVE,
            created_at=now,
            expires_at=now + timedelta(seconds=self._max_session_seconds),
        )
        self._sessions[session.session_id] = session
        self._owners[session.session_id] = owner_key
        return session

    def get(self, session_id: str, *, owner_key: str) -> CameraSession | None:
        session = self._sessions.get(session_id)
        if session is None or self._owners.get(session_id) != owner_key:
            return None
        if session.status == CameraSessionStatus.ACTIVE and session.expires_at <= self._now():
            session = session.model_copy(update={"status": CameraSessionStatus.EXPIRED})
            self._sessions[session_id] = session
        return session

    def stop(self, session_id: str, *, owner_key: str) -> CameraSession | None:
        session = self.get(session_id, owner_key=owner_key)
        if session is None:
            return None
        if session.status == CameraSessionStatus.ACTIVE:
            session = session.model_copy(update={"status": CameraSessionStatus.STOPPED})
            self._sessions[session_id] = session
        return session

    def owned_session_ids(self, *, owner_key: str) -> tuple[str, ...]:
        return tuple(
            session_id
            for session_id, session_owner in self._owners.items()
            if session_owner == owner_key and self._sessions.get(session_id) is not None
        )

    def is_active_for_capture(self, session_id: str) -> bool:
        owner_key = self._owners.get(session_id)
        if owner_key is None:
            return False
        session = self.get(session_id, owner_key=owner_key)
        return session is not None and session.status == CameraSessionStatus.ACTIVE

    def validate_observation(
        self,
        observation: CameraObservation,
        *,
        owner_key: str,
    ) -> CameraSession:
        session = self.get(observation.session_id, owner_key=owner_key)
        if session is None:
            raise LookupError("camera session was not found")
        if session.status != CameraSessionStatus.ACTIVE:
            raise PermissionError("camera session is not active")
        if observation.confidence < self._minimum_observation_confidence:
            raise ValueError("camera observation confidence is below the minimum")
        if not session.created_at <= observation.observed_at <= self._now() + timedelta(seconds=5):
            raise ValueError("camera observation timestamp is outside its session")
        return session

    def validate_capture_observation(self, observation: CameraObservation) -> CameraSession:
        """Internal worker validation; the worker has no external owner-controlled input."""
        session = self._sessions.get(observation.session_id)
        if session is None:
            raise LookupError("camera session was not found")
        owner = self._owners.get(observation.session_id, "")
        return self.validate_observation(observation, owner_key=owner)
