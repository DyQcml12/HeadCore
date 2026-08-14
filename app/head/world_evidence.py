from __future__ import annotations

import hashlib

from app.head.contracts import CognitiveFact, CognitiveFactKind, CognitiveFactSourceKind
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldObservation,
    WorldSourceCapability,
)


MIN_AUTOMATIC_FACT_CONFIDENCE = 0.8

WORLD_EVIDENCE_FIELD_WHITELIST: dict[
    WorldSourceCapability, tuple[tuple[str, str], ...]
] = {
    WorldSourceCapability.WEATHER_CURRENT: (
        ("weather", "condition"),
        ("temperature_c", "temperature_c"),
        ("humidity_percent", "humidity_percent"),
    ),
    WorldSourceCapability.NEWS: (
        ("title", "title"),
        ("published_at", "published_at"),
        ("source_name", "source_name"),
        ("url", "url"),
    ),
    WorldSourceCapability.POLICY: (
        ("title", "title"),
        ("published_at", "published_at"),
        ("url", "url"),
    ),
    WorldSourceCapability.MAP_ROUTE: (
        ("mode", "mode"),
        ("duration_seconds", "duration_seconds"),
        ("distance_meters", "distance_meters"),
    ),
}

_CAPABILITY_KEY_PREFIX: dict[WorldSourceCapability, str] = {
    WorldSourceCapability.WEATHER_CURRENT: "weather",
    WorldSourceCapability.NEWS: "news",
    WorldSourceCapability.POLICY: "policy",
    WorldSourceCapability.MAP_ROUTE: "route",
}


def cognitive_facts_from_world_result(
    result: WorldAcquisitionResult,
    *,
    version: int = 1,
) -> tuple[CognitiveFact, ...]:
    """Convert only allowlisted, public, fresh world observations into facts."""
    if version < 1:
        raise ValueError("world evidence fact version must be positive")
    fields = WORLD_EVIDENCE_FIELD_WHITELIST.get(result.batch.capability)
    if fields is None:
        return ()
    facts: list[CognitiveFact] = []
    for observation in result.batch.observations:
        facts.extend(
            _capability_facts(
                observation,
                capability=result.batch.capability,
                fields=fields,
                source_id=result.batch.source_id,
                version=version,
            )
        )
    return tuple(facts)


def _capability_facts(
    observation: WorldObservation,
    *,
    capability: WorldSourceCapability,
    fields: tuple[tuple[str, str], ...],
    source_id: str,
    version: int,
) -> tuple[CognitiveFact, ...]:
    if (
        observation.capability != capability
        or observation.sensitivity != DataSensitivity.PUBLIC
        or observation.confidence < MIN_AUTOMATIC_FACT_CONFIDENCE
        or not observation.evidence
    ):
        return ()
    location_key = _capability_location_key(observation, capability)
    if not location_key:
        return ()
    facts = []
    for payload_key, fact_field in fields:
        raw_value = observation.payload.get(payload_key)
        value = str(raw_value or "").strip()
        if not value or len(value) > 240 or any(char in value for char in "\r\n\x00"):
            continue
        key = f"{_CAPABILITY_KEY_PREFIX[capability]}.{location_key}.{fact_field}"
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


def _capability_location_key(
    observation: WorldObservation,
    capability: WorldSourceCapability,
) -> str:
    if capability == WorldSourceCapability.WEATHER_CURRENT:
        key = str(
            observation.payload.get("adcode") or observation.payload.get("location_id") or ""
        ).strip()
        return key if key and len(key) <= 32 and key.isalnum() else ""
    if capability in {WorldSourceCapability.NEWS, WorldSourceCapability.POLICY}:
        title = str(observation.payload.get("title") or "").strip()
        if not title:
            return ""
        extra = str(observation.payload.get("source_name") or observation.payload.get("url") or "")
        return _digest_key(f"{title}\n{extra}")
    if capability == WorldSourceCapability.MAP_ROUTE:
        origin = str(observation.payload.get("origin_id") or "").strip()
        destination = str(observation.payload.get("destination_id") or "").strip()
        if (
            origin
            and destination
            and len(origin) <= 32
            and len(destination) <= 32
            and origin.isalnum()
            and destination.isalnum()
        ):
            return f"{origin}.{destination}"
        mode = str(observation.payload.get("mode") or "").strip()
        return _digest_key(f"{mode}\n{observation.observation_id}")
    return ""


def _digest_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _fact_id(observation_id: str, key: str) -> str:
    digest = hashlib.sha256(f"{observation_id}\n{key}".encode("utf-8")).hexdigest()[:24]
    return f"world-{digest}"
