from __future__ import annotations

from dataclasses import dataclass

from app.camera.contracts import CameraObservation


@dataclass(frozen=True)
class CameraSceneState:
    """A bounded scene fact derived only from confirmed allowlisted labels."""

    state_id: str
    facts: tuple[str, ...] = ()
    confidence: float = 0.0
    reason_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "state_id": self.state_id,
            "facts": list(self.facts),
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
        }


def derive_scene_state(observation: CameraObservation) -> CameraSceneState:
    """Summarize explicit visual labels without adding human-like inference."""

    objects = set(observation.objects)
    poses = set(observation.pose_labels)
    gestures = set(observation.gesture_labels)
    scene = observation.scene_label

    if scene == "street" or "car" in objects:
        return _state(observation, "street_vehicle", "street_scene")
    if scene == "desk" and "typing" in gestures:
        return _state(observation, "desk_work", "desk_scene", "activity:typing")
    if scene == "desk" and "writing" in gestures:
        return _state(observation, "desk_work", "desk_scene", "activity:writing")
    if scene == "desk" and objects.intersection({"keyboard", "laptop", "book", "phone"}):
        return _state(observation, "desk_setup", "desk_scene")
    if "person" in objects and (scene in {"indoor", "room", "desk"} or poses):
        return _state(observation, "person_present", "person_present")
    if scene:
        return _state(observation, f"scene:{scene}", f"scene:{scene}")

    return CameraSceneState(
        state_id="unclassified",
        confidence=0.0,
        reason_codes=("insufficient_allowlisted_labels",),
    )


def _state(observation: CameraObservation, state_id: str, *facts: str) -> CameraSceneState:
    return CameraSceneState(
        state_id=state_id,
        facts=tuple(dict.fromkeys(facts)),
        confidence=round(observation.confidence, 4),
    )
