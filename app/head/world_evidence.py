from __future__ import annotations

import hashlib
import re

from app.head.contracts import CognitiveFact, CognitiveFactKind, CognitiveFactSourceKind
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldObservation,
    WorldSourceCapability,
)


MIN_AUTOMATIC_FACT_CONFIDENCE = 0.8

_IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,95}")

# Flat observation payloads: (payload_key, fact_field).
WORLD_EVIDENCE_FIELD_WHITELIST: dict[
    WorldSourceCapability, tuple[tuple[str, str], ...]
] = {
    WorldSourceCapability.WEATHER_CURRENT: (
        ("weather", "condition"),
        ("temperature_c", "temperature_c"),
        ("humidity_percent", "humidity_percent"),
    ),
}

# List payloads: (list_payload_key, item_key_payload_field, fields).
# Each list item contributes one fact per field; item_key_payload_field keeps the
# item unique within the observation's location key.
_LIST_FIELD_SPECS: dict[
    WorldSourceCapability, tuple[str, str, tuple[tuple[str, str], ...]]
] = {
    WorldSourceCapability.WEATHER_FORECAST: (
        "casts",
        "date",
        (
            ("day_weather", "day_weather"),
            ("night_weather", "night_weather"),
            ("day_temperature_c", "day_temperature_c"),
            ("night_temperature_c", "night_temperature_c"),
        ),
    ),
    WorldSourceCapability.NEWS: (
        "items",
        "title",
        (
            ("title", "title"),
            ("published_at", "published_at"),
            ("url", "url"),
        ),
    ),
    WorldSourceCapability.POLICY: (
        "items",
        "title",
        (
            ("title", "title"),
            ("published_at", "published_at"),
            ("url", "url"),
        ),
    ),
    WorldSourceCapability.MAP_ROUTE: (
        "routes",
        "option",
        (
            ("duration_seconds", "duration_seconds"),
            ("distance_m", "distance_meters"),
        ),
    ),
}

_CAPABILITY_KEY_PREFIX: dict[WorldSourceCapability, str] = {
    WorldSourceCapability.WEATHER_CURRENT: "weather",
    WorldSourceCapability.WEATHER_FORECAST: "weather",
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
    facts: list[CognitiveFact] = []
    for observation in result.batch.observations:
        facts.extend(
            _capability_facts(
                observation,
                capability=result.batch.capability,
                source_id=result.batch.source_id,
                version=version,
            )
        )
    return tuple(facts)


def _capability_facts(
    observation: WorldObservation,
    *,
    capability: WorldSourceCapability,
    source_id: str,
    version: int,
) -> tuple[CognitiveFact, ...]:
    if not _passes_gates(observation, capability):
        return ()
    prefix = _CAPABILITY_KEY_PREFIX.get(capability)
    if not prefix:
        return ()
    location_key = _capability_location_key(observation, capability)
    if not location_key:
        return ()

    flat_fields = WORLD_EVIDENCE_FIELD_WHITELIST.get(capability)
    if flat_fields is not None:
        return tuple(
            _fact(observation, f"{prefix}.{location_key}.{fact_field}", value, source_id, version)
            for payload_key, fact_field in flat_fields
            if (value := _valid_value(observation.payload.get(payload_key)))
        )

    list_spec = _LIST_FIELD_SPECS.get(capability)
    if list_spec is None:
        return ()
    return tuple(_list_facts(observation, prefix, location_key, list_spec, source_id, version))


def _list_facts(
    observation: WorldObservation,
    prefix: str,
    location_key: str,
    spec: tuple[str, str, tuple[tuple[str, str], ...]],
    source_id: str,
    version: int,
) -> tuple[CognitiveFact, ...]:
    list_key, item_key_field, fields = spec
    items = observation.payload.get(list_key)
    if not isinstance(items, list):
        return ()
    facts: list[CognitiveFact] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_suffix = _item_key_suffix(str(item.get(item_key_field) or ""))
        if not item_suffix:
            continue
        for payload_key, fact_field in fields:
            value = _valid_value(item.get(payload_key))
            if not value:
                continue
            facts.append(
                _fact(
                    observation,
                    f"{prefix}.{location_key}.{item_suffix}.{fact_field}",
                    value,
                    source_id,
                    version,
                )
            )
    return tuple(facts)


def _fact(
    observation: WorldObservation,
    key: str,
    value: str,
    source_id: str,
    version: int,
) -> CognitiveFact:
    return CognitiveFact(
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


def _passes_gates(observation: WorldObservation, capability: WorldSourceCapability) -> bool:
    return (
        observation.capability == capability
        and observation.sensitivity == DataSensitivity.PUBLIC
        and observation.confidence >= MIN_AUTOMATIC_FACT_CONFIDENCE
        and bool(observation.evidence)
    )


def _valid_value(raw: object | None) -> str:
    value = str(raw or "").strip()
    if not value or len(value) > 240 or any(char in value for char in "\r\n\x00"):
        return ""
    return value


def _capability_location_key(
    observation: WorldObservation,
    capability: WorldSourceCapability,
) -> str:
    if capability in {WorldSourceCapability.WEATHER_CURRENT, WorldSourceCapability.WEATHER_FORECAST}:
        key = str(
            observation.payload.get("adcode") or observation.payload.get("location_id") or ""
        ).strip()
        return key if key and len(key) <= 32 and key.isalnum() else ""
    if capability in {WorldSourceCapability.NEWS, WorldSourceCapability.POLICY}:
        topic = str(observation.payload.get("topic") or "").strip()
        return _safe_location_key(topic)
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


def _safe_location_key(value: str) -> str:
    if not value:
        return ""
    if _IDENTIFIER_RE.fullmatch(value):
        return value[:32]
    return _digest_key(value)


def _item_key_suffix(value: str) -> str:
    if not value:
        return ""
    if _IDENTIFIER_RE.fullmatch(value):
        return value[:48]
    return _digest_key(value)


def _digest_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _fact_id(observation_id: str, key: str) -> str:
    digest = hashlib.sha256(f"{observation_id}\n{key}".encode("utf-8")).hexdigest()[:24]
    return f"world-{digest}"
