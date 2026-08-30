from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_ALLOWED_LABELS = {
    "objects": frozenset({"backpack", "book", "bottle", "car", "cat", "chair", "cup", "desk", "dog", "keyboard", "laptop", "mouse", "person", "phone", "screen", "table"}),
    "pose_labels": frozenset({"standing", "sitting", "walking", "leaning", "head_down"}),
    "gesture_labels": frozenset({"pointing", "raised_hand", "waving", "writing", "typing"}),
    # These are visual cues only, never statements of emotion or identity.
    "facial_cues": frozenset({"brow_furrow_detected", "eyes_closed_detected", "gaze_away_detected", "head_down_detected"}),
}
_ALLOWED_SCENES = frozenset({"desk", "indoor", "outdoor", "room", "street"})


class CameraSessionStatus(StrEnum):
    DISABLED = "disabled"
    ACTIVE = "active"
    EXPIRED = "expired"
    STOPPED = "stopped"


class CameraSessionMode(StrEnum):
    REAL = "real"
    DEMO = "demo"


class CameraDemoScenario(StrEnum):
    DESK_WORK = "desk_work"
    DESK_SETUP = "desk_setup"
    STREET_VEHICLE = "street_vehicle"
    PERSON_PRESENT = "person_present"


class CameraContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)


class CameraSessionStartRequest(CameraContract):
    consent_granted: bool
    camera_slot: int = Field(default=0, ge=0, le=15)
    mode: CameraSessionMode = CameraSessionMode.REAL
    demo_scenario: CameraDemoScenario | None = None

    @model_validator(mode="after")
    def require_explicit_consent(self) -> CameraSessionStartRequest:
        if not self.consent_granted:
            raise ValueError("camera consent must be explicitly granted")
        if self.mode == CameraSessionMode.REAL and self.demo_scenario is not None:
            raise ValueError("real camera sessions cannot select a demo scenario")
        return self


class CameraSession(CameraContract):
    session_id: str = Field(min_length=20, max_length=80)
    camera_slot: int = Field(ge=0, le=15)
    status: CameraSessionStatus
    mode: CameraSessionMode = CameraSessionMode.REAL
    demo_scenario: CameraDemoScenario | None = None
    created_at: datetime
    expires_at: datetime


class CameraObservation(CameraContract):
    session_id: str = Field(min_length=20, max_length=80)
    scene_label: str = Field(default="", max_length=64)
    objects: tuple[str, ...] = Field(default_factory=tuple, max_length=12)
    pose_labels: tuple[str, ...] = Field(default_factory=tuple, max_length=4)
    gesture_labels: tuple[str, ...] = Field(default_factory=tuple, max_length=4)
    facial_cues: tuple[str, ...] = Field(default_factory=tuple, max_length=4)
    confidence: float = Field(ge=0.0, le=1.0)
    observed_at: datetime

    @field_validator("scene_label", mode="before")
    @classmethod
    def normalize_scene_label(cls, value: object) -> str:
        label = _normalize_label(value, field_name="scene_label") if value else ""
        if label and label not in _ALLOWED_SCENES:
            raise ValueError("scene_label is not allowlisted")
        return label

    @field_validator("objects", "pose_labels", "gesture_labels", "facial_cues")
    @classmethod
    def validate_labels(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        labels = tuple(_normalize_label(item, field_name=info.field_name) for item in value)
        if any(label not in _ALLOWED_LABELS[info.field_name] for label in labels):
            raise ValueError(f"{info.field_name} contains a non-allowlisted label")
        return labels


def _normalize_label(value: object, *, field_name: str) -> str:
    label = str(value).strip().lower()
    if not label or len(label) > 64 or any(not (char.isalnum() or char in {"_", "-"}) for char in label):
        raise ValueError(f"{field_name} must contain a bounded machine label")
    return label
