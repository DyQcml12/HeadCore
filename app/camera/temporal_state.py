from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import timedelta

from app.camera.contracts import CameraObservation


@dataclass(frozen=True)
class CameraTemporalUpdate:
    observation: CameraObservation
    changes: tuple[str, ...] = ()


class CameraTemporalState:
    """Confirms repeated label-only observations and their bounded changes."""

    def __init__(self, *, confirmation_count: int, window_seconds: int) -> None:
        if not 2 <= confirmation_count <= 5:
            raise ValueError("camera confirmation_count must be between 2 and 5")
        if not 2 <= window_seconds <= 60:
            raise ValueError("camera temporal window_seconds must be between 2 and 60")
        self._confirmation_count = confirmation_count
        self._window = timedelta(seconds=window_seconds)
        self._history: dict[str, dict[tuple[str, str], deque]] = {}
        self._current: dict[str, set[tuple[str, str]]] = {}
        self._missing_counts: dict[str, dict[tuple[str, str], int]] = {}
        self._latest: dict[str, CameraTemporalUpdate] = {}

    def observe(self, observation: CameraObservation) -> CameraTemporalUpdate | None:
        history = self._history.setdefault(observation.session_id, {})
        cutoff = observation.observed_at - self._window
        for samples in history.values():
            while samples and samples[0] < cutoff:
                samples.popleft()

        received = set(_labels(observation))
        stable_additions: set[tuple[str, str]] = set()
        for key in received:
            samples = history.setdefault(key, deque())
            samples.append(observation.observed_at)
            if len(samples) >= self._confirmation_count:
                stable_additions.add(key)

        previous = self._current.setdefault(observation.session_id, set())
        missing_counts = self._missing_counts.setdefault(observation.session_id, {})
        next_state = set(previous)
        next_state.update(stable_additions)
        for key in previous:
            if key in received:
                missing_counts.pop(key, None)
                continue
            missing_counts[key] = missing_counts.get(key, 0) + 1
            if missing_counts[key] >= self._confirmation_count:
                next_state.discard(key)
                missing_counts.pop(key, None)

        if not next_state:
            self._current[observation.session_id] = set()
            self._latest.pop(observation.session_id, None)
            return None
        changes = tuple(
            [f"appeared:{category}:{label}" for category, label in sorted(next_state - previous)]
            + [f"disappeared:{category}:{label}" for category, label in sorted(previous - next_state)]
        )
        self._current[observation.session_id] = next_state
        update = CameraTemporalUpdate(
            observation=_observation_from_state(observation, next_state),
            changes=changes,
        )
        self._latest[observation.session_id] = update
        return update

    def latest(self, session_id: str) -> CameraTemporalUpdate | None:
        return self._latest.get(session_id)

    def remove_session(self, session_id: str) -> None:
        self._history.pop(session_id, None)
        self._current.pop(session_id, None)
        self._missing_counts.pop(session_id, None)
        self._latest.pop(session_id, None)


def _labels(observation: CameraObservation) -> tuple[tuple[str, str], ...]:
    labels: list[tuple[str, str]] = []
    if observation.scene_label:
        labels.append(("scene_label", observation.scene_label))
    labels.extend(("objects", label) for label in observation.objects)
    labels.extend(("pose_labels", label) for label in observation.pose_labels)
    labels.extend(("gesture_labels", label) for label in observation.gesture_labels)
    labels.extend(("facial_cues", label) for label in observation.facial_cues)
    return tuple(labels)


def _observation_from_state(
    observation: CameraObservation,
    state: set[tuple[str, str]],
) -> CameraObservation:
    grouped: dict[str, list[str]] = {
        "scene_label": [],
        "objects": [],
        "pose_labels": [],
        "gesture_labels": [],
        "facial_cues": [],
    }
    for category, label in sorted(state):
        grouped[category].append(label)
    return observation.model_copy(
        update={
            "scene_label": grouped["scene_label"][0] if grouped["scene_label"] else "",
            "objects": tuple(grouped["objects"]),
            "pose_labels": tuple(grouped["pose_labels"]),
            "gesture_labels": tuple(grouped["gesture_labels"]),
            "facial_cues": tuple(grouped["facial_cues"]),
        }
    )
