from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from app.camera.contracts import CameraObservation
from app.world.contracts import DataSensitivity, WorldEvidence, WorldObservation, WorldSourceCapability


def camera_observation_to_world_observation(
    observation: CameraObservation,
    *,
    ttl_seconds: int,
) -> WorldObservation:
    if not 1 <= ttl_seconds <= 300:
        raise ValueError("camera observation ttl_seconds must be between 1 and 300")
    payload = {
        "scene_label": observation.scene_label,
        "objects": observation.objects,
        "pose_labels": observation.pose_labels,
        "gesture_labels": observation.gesture_labels,
        "facial_cues": observation.facial_cues,
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    evidence = WorldEvidence(
        source_id="local-camera",
        source_uri="local://camera/structured-observation",
        retrieved_at=observation.observed_at,
        content_hash=digest,
    )
    return WorldObservation(
        observation_id=f"camera:{digest[:24]}",
        capability=WorldSourceCapability.VISION_EVENT,
        observed_at=observation.observed_at,
        expires_at=observation.observed_at + timedelta(seconds=ttl_seconds),
        confidence=observation.confidence,
        payload=payload,
        evidence=(evidence,),
        sensitivity=DataSensitivity.PRIVATE,
    )
