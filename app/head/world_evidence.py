from __future__ import annotations

import hashlib
from typing import Iterable

from app.head.contracts import CognitiveFact, CognitiveFactKind, CognitiveFactSourceKind
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldObservation,
    WorldSourceCapability,
)


MIN_AUTOMATIC_FACT_CONFIDENCE = 0.8


def cognitive_facts_from_world_result(
    result: WorldAcquisitionResult,
    *,
    version: int = 1,
) -> tuple[CognitiveFact, ...]:
    """Convert only allowlisted, public, fresh world observations into facts."""
    if version < 1:
        raise ValueError("world evidence fact version must be positive")
    if result.batch.capability != WorldSourceCapability.WEATHER_CURRENT:
        return ()
    facts: list[CognitiveFact] = []
    for observation in result.batch.observations:
        facts.extend(
            _weather_facts(
                observation,
                source_id=result.batch.source_id,
                version=version,
            )
        )
    return tuple(facts)


def _weather_facts(
    observation: WorldObservation,
    *,
    source_id: str,
    version: int,
) -> Iterable[CognitiveFact]:
    if (
        observation.capability != WorldSourceCapability.WEATHER_CURRENT
        or observation.sensitivity != DataSensitivity.PUBLIC
        or observation.confidence < MIN_AUTOMATIC_FACT_CONFIDENCE
        or not observation.evidence
    ):
        return ()
    location_key = str(
        observation.payload.get("adcode") or observation.payload.get("location_id") or ""
    ).strip()
    if not location_key or len(location_key) > 32 or not location_key.isalnum():
        return ()
    fields = {
        "condition": observation.payload.get("weather"),
        "temperature_c": observation.payload.get("temperature_c"),
        "humidity_percent": observation.payload.get("humidity_percent"),
    }
    facts = []
    for name, raw_value in fields.items():
        value = str(raw_value or "").strip()
        if not value or len(value) > 240 or any(char in value for char in "\r\n\x00"):
            continue
        key = f"weather.{location_key}.{name}"
        facts.append(
            CognitiveFact(
                fact_id=_fact_id(observation.observation_id, key),
                key=key,
                value=value,
                source_id=source_id,
                observed_at=observation.observed_at.isoformat(),
                expires_at=observation.expires_at.isoformat(),
                confidence=observation.confidence,
                version=version,
                kind=CognitiveFactKind.OBSERVATION,
                source_kind=CognitiveFactSourceKind.WORLD_EVIDENCE,
                supporting_source_ids=(source_id,),
            )
        )
    return tuple(facts)


def _fact_id(observation_id: str, key: str) -> str:
    digest = hashlib.sha256(f"{observation_id}\n{key}".encode("utf-8")).hexdigest()[:24]
    return f"world-{digest}"
