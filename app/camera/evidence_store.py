from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.camera.temporal_state import CameraTemporalUpdate


class CameraContextProvider(Protocol):
    def latest_context(self) -> str: ...


@dataclass(frozen=True)
class _StoredCameraContext:
    observed_at: datetime
    current: str
    changes: str


class CameraEvidenceStore:
    """Keep the latest temporally-confirmed camera context per session.

    Labels only, never frames. This is the L1 bridge that lets chat attention
    (:func:`app.camera.attention.select_camera_context`) see what the camera
    confirmed most recently, so visual facts can enter the dialogue evidence
    chain without any raw media leaving the capture process.
    """

    def __init__(self, *, max_age_seconds: int = 300) -> None:
        if not 1 <= max_age_seconds <= 3600:
            raise ValueError("camera context max_age_seconds must be between 1 and 3600")
        self._max_age = timedelta(seconds=max_age_seconds)
        self._by_session: dict[str, _StoredCameraContext] = {}
        self._latest_session: str | None = None

    def record_update(self, update: CameraTemporalUpdate) -> None:
        current = _render_observation(update.observation)
        changes = " | ".join(update.changes[:8]) if update.changes else ""
        self._by_session[update.observation.session_id] = _StoredCameraContext(
            observed_at=update.observation.observed_at,
            current=current,
            changes=changes,
        )
        self._latest_session = update.observation.session_id
        self.prune(update.observation.observed_at)

    def remove_session(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)
        if self._latest_session == session_id:
            self._latest_session = None

    def latest_context(self) -> str:
        self.prune(datetime.now(timezone.utc))
        if self._latest_session is None:
            return ""
        stored = self._by_session.get(self._latest_session)
        if stored is None:
            self._latest_session = None
            return ""
        text = stored.current
        if stored.changes:
            text = f"{text} ; changes: {stored.changes}"
        return text[:240]

    def prune(self, now: datetime) -> None:
        cutoff = now - self._max_age
        stale = [
            session_id
            for session_id, stored in self._by_session.items()
            if stored.observed_at < cutoff
        ]
        for session_id in stale:
            del self._by_session[session_id]
            if self._latest_session == session_id:
                self._latest_session = None


def _render_observation(observation: object) -> str:
    parts: list[str] = []
    scene_label = str(getattr(observation, "scene_label", ""))
    objects = tuple(getattr(observation, "objects", ()))
    pose_labels = tuple(getattr(observation, "pose_labels", ()))
    gesture_labels = tuple(getattr(observation, "gesture_labels", ()))
    facial_cues = tuple(getattr(observation, "facial_cues", ()))
    if scene_label:
        parts.append(f"scene: {scene_label}")
    if objects:
        parts.append("objects: " + ", ".join(objects))
    if pose_labels:
        parts.append("pose: " + ", ".join(pose_labels))
    if gesture_labels:
        parts.append("gesture: " + ", ".join(gesture_labels))
    if facial_cues:
        parts.append("visual cues: " + ", ".join(facial_cues))
    return " | ".join(parts)
