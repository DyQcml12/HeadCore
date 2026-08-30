from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.camera.scene_state import CameraSceneState, derive_scene_state
from app.camera.temporal_state import CameraTemporalUpdate


class CameraContextProvider(Protocol):
    def latest_context(self) -> str: ...


@dataclass(frozen=True)
class _StoredCameraContext:
    observed_at: datetime
    current: str
    changes: str
    scene_state: CameraSceneState
    scene_label: str
    objects: tuple[str, ...]
    pose_labels: tuple[str, ...]
    gesture_labels: tuple[str, ...]
    facial_cues: tuple[str, ...]


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
        scene_state = derive_scene_state(update.observation)
        current = _render_observation(update.observation, scene_state=scene_state)
        changes = list(update.changes[:8])
        previous = self._by_session.get(update.observation.session_id)
        if previous and previous.scene_state.state_id != scene_state.state_id:
            changes.append(
                f"state:{previous.scene_state.state_id}->{scene_state.state_id}"
            )
        self._by_session[update.observation.session_id] = _StoredCameraContext(
            observed_at=update.observation.observed_at,
            current=current,
            changes=" | ".join(changes[:8]),
            scene_state=scene_state,
            scene_label=update.observation.scene_label,
            objects=tuple(update.observation.objects),
            pose_labels=tuple(update.observation.pose_labels),
            gesture_labels=tuple(update.observation.gesture_labels),
            facial_cues=tuple(update.observation.facial_cues),
        )
        self._latest_session = update.observation.session_id
        self.prune(update.observation.observed_at)

    def remove_session(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)
        if self._latest_session == session_id:
            self._latest_session = None

    def latest_context(self) -> str:
        snapshot = self.latest_snapshot()
        if not snapshot["available"]:
            return ""
        stored = self._by_session.get(str(snapshot["session_id"]))
        if stored is None:
            return ""
        text = stored.current
        if stored.changes:
            text = f"{text} ; changes: {stored.changes}"
        return text[:240]

    def latest_snapshot(self, session_id: str | None = None) -> dict[str, object]:
        """Return a structured, label-only snapshot for a local UI consumer."""

        self.prune(datetime.now(timezone.utc))
        selected_session = session_id or self._latest_session
        stored = self._by_session.get(selected_session) if selected_session else None
        if stored is None:
            return {
                "available": False,
                "reason": "no_confirmed_observation",
            }
        return {
            "available": True,
            "session_id": selected_session,
            "scene_state": stored.scene_state.state_id,
            "scene_facts": list(stored.scene_state.facts),
            "scene_confidence": stored.scene_state.confidence,
            "scene_label": stored.scene_label,
            "objects": list(stored.objects),
            "pose_labels": list(stored.pose_labels),
            "gesture_labels": list(stored.gesture_labels),
            "facial_cues": list(stored.facial_cues),
            "changes": stored.changes.split(" | ") if stored.changes else [],
            "observed_at": stored.observed_at,
        }

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


def _render_observation(
    observation: object,
    *,
    scene_state: CameraSceneState | None = None,
) -> str:
    parts: list[str] = []
    if scene_state and scene_state.state_id != "unclassified":
        parts.append(f"scene_state: {scene_state.state_id}")
        if scene_state.facts:
            parts.append("scene_facts: " + ", ".join(scene_state.facts))
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
