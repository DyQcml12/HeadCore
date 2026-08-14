from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class WorldSourceKind(StrEnum):
    API = "api"
    RSS = "rss"
    HTTP = "http"
    SENSOR = "sensor"
    USER = "user"


class WorldSourceCapability(StrEnum):
    IP_LOCATION = "ip_location"
    WEATHER_CURRENT = "weather_current"
    WEATHER_FORECAST = "weather_forecast"
    NEWS = "news"
    POLICY = "policy"
    FINANCE = "finance"
    MAP_ROUTE = "map_route"
    MAP_PLACE = "map_place"
    VISION_EVENT = "vision_event"


class DataSensitivity(StrEnum):
    PUBLIC = "public"
    COARSE_LOCATION = "coarse_location"
    PRECISE_LOCATION = "precise_location"
    PRIVATE = "private"


_SENSITIVE_PARAMETER_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "key",
    "password",
    "secret",
    "token",
}


@dataclass(frozen=True)
class WorldEvidence:
    source_id: str
    source_uri: str
    retrieved_at: datetime
    content_hash: str
    published_at: datetime | None = None
    license_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("evidence source_id must not be empty")
        if not self.source_uri.strip():
            raise ValueError("evidence source_uri must not be empty")
        if len(self.content_hash) < 16:
            raise ValueError("evidence content_hash must be a digest, not raw content")


@dataclass(frozen=True)
class WorldObservation:
    observation_id: str
    capability: WorldSourceCapability
    observed_at: datetime
    expires_at: datetime
    confidence: float
    payload: Mapping[str, Any]
    evidence: tuple[WorldEvidence, ...]
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id must not be empty")
        if self.expires_at <= self.observed_at:
            raise ValueError("observation expires_at must be after observed_at")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("observation confidence must be between 0 and 1")
        if not self.evidence:
            raise ValueError("observation requires at least one evidence record")


@dataclass(frozen=True)
class WorldObservationBatch:
    source_id: str
    capability: WorldSourceCapability
    fetched_at: datetime
    observations: tuple[WorldObservation, ...]

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("batch source_id must not be empty")
        if not self.observations:
            raise ValueError("batch requires at least one observation")
        if any(item.capability != self.capability for item in self.observations):
            raise ValueError("batch observation capability mismatch")


@dataclass(frozen=True)
class WorldSourceDefinition:
    source_id: str
    kind: WorldSourceKind
    capabilities: frozenset[WorldSourceCapability]
    enabled: bool = False
    legal_approved: bool = False
    terms_url: str = ""
    allowed_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized = self.source_id.strip().lower()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("world source_id must be non-empty and contain no whitespace")
        if not self.capabilities:
            raise ValueError("world source must declare at least one capability")
        object.__setattr__(self, "source_id", normalized)
        object.__setattr__(
            self,
            "allowed_hosts",
            tuple(sorted({host.strip().lower() for host in self.allowed_hosts if host.strip()})),
        )


@dataclass(frozen=True)
class WorldQuery:
    source_id: str
    capability: WorldSourceCapability
    parameters: Mapping[str, str] = field(default_factory=dict)
    ttl_seconds: int = 900
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC
    consent_granted: bool = False
    cache_partition: str = "public"

    def __post_init__(self) -> None:
        normalized_source = self.source_id.strip().lower()
        if not normalized_source:
            raise ValueError("query source_id must not be empty")
        if self.ttl_seconds <= 0:
            raise ValueError("query ttl_seconds must be positive")
        if not self.cache_partition.strip():
            raise ValueError("query cache_partition must not be empty")
        normalized_parameters: dict[str, str] = {}
        for raw_key, raw_value in self.parameters.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("query parameter names must not be empty")
            if key.lower() in _SENSITIVE_PARAMETER_NAMES:
                raise ValueError("API keys and credentials belong to source adapters, not queries")
            normalized_parameters[key] = str(raw_value).strip()
        object.__setattr__(self, "source_id", normalized_source)
        object.__setattr__(self, "parameters", normalized_parameters)
        object.__setattr__(self, "cache_partition", self.cache_partition.strip())


@dataclass(frozen=True)
class WorldAcquisitionResult:
    batch: WorldObservationBatch
    cache_hit: bool
    shared_request: bool
    cache_key: str
