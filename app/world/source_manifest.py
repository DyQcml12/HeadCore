from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.world.contracts import WorldSourceCapability, WorldSourceKind

_MAX_MANIFEST_BYTES = 1_048_576
_REGIONS = frozenset({"domestic", "international", "global"})
_AUTOMATION_POLICIES = frozenset(
    {"api", "feed", "review_required", "robots_blocked", "approved_page"}
)
_ENTRY_FIELDS = frozenset(
    {
        "source_id",
        "display_name",
        "region",
        "kind",
        "capabilities",
        "entry_url",
        "allowed_hosts",
        "refresh_seconds",
        "enabled",
        "legal_approved",
        "requires_api_key",
        "discovery_only",
        "terms_url",
        "robots_url",
        "automation_policy",
    }
)


@dataclass(frozen=True)
class WorldSourceCatalogEntry:
    source_id: str
    display_name: str
    region: str
    kind: WorldSourceKind
    capabilities: frozenset[WorldSourceCapability]
    entry_url: str
    allowed_hosts: tuple[str, ...]
    refresh_seconds: int
    enabled: bool
    legal_approved: bool
    requires_api_key: bool
    discovery_only: bool
    terms_url: str = ""
    robots_url: str = ""
    automation_policy: str = "review_required"


@dataclass(frozen=True)
class WorldSourceManifest:
    version: int
    sources: tuple[WorldSourceCatalogEntry, ...]


def load_source_manifest(path: str | Path) -> WorldSourceManifest:
    manifest_path = Path(path)
    raw = manifest_path.read_bytes()
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ValueError("world source manifest is too large")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("world source manifest must be UTF-8 JSON") from exc
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("world source manifest version must be 1")
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("world source manifest sources must be a list")

    entries = tuple(_parse_entry(value) for value in raw_sources)
    source_ids = [entry.source_id for entry in entries]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("world source manifest contains duplicate source ids")
    return WorldSourceManifest(version=1, sources=entries)


def _parse_entry(value: object) -> WorldSourceCatalogEntry:
    if not isinstance(value, dict):
        raise ValueError("world source manifest entries must be objects")
    unknown_fields = set(value) - _ENTRY_FIELDS
    if unknown_fields:
        raise ValueError("world source manifest contains unknown fields")

    source_id = _required_text(value, "source_id").lower()
    if any(character.isspace() for character in source_id):
        raise ValueError("world source id must not contain whitespace")
    display_name = _required_text(value, "display_name")
    region = _required_text(value, "region").lower()
    if region not in _REGIONS:
        raise ValueError("world source region is invalid")
    try:
        kind = WorldSourceKind(_required_text(value, "kind"))
    except ValueError as exc:
        raise ValueError("world source kind is invalid") from exc

    raw_capabilities = value.get("capabilities")
    if not isinstance(raw_capabilities, list) or not raw_capabilities:
        raise ValueError("world source capabilities must be a non-empty list")
    try:
        capabilities = frozenset(WorldSourceCapability(str(item)) for item in raw_capabilities)
    except ValueError as exc:
        raise ValueError("world source capability is invalid") from exc

    raw_hosts = value.get("allowed_hosts")
    if not isinstance(raw_hosts, list) or not raw_hosts:
        raise ValueError("world source allowed_hosts must be a non-empty list")
    allowed_hosts = tuple(sorted({_host_text(item) for item in raw_hosts}))
    entry_url = _validated_url(_required_text(value, "entry_url"), allowed_hosts)
    terms_url = _optional_url(value.get("terms_url"), allowed_hosts=None)
    robots_url = _optional_url(value.get("robots_url"), allowed_hosts=allowed_hosts)

    refresh_seconds = value.get("refresh_seconds")
    if not isinstance(refresh_seconds, int) or not 60 <= refresh_seconds <= 86_400:
        raise ValueError("world source refresh_seconds must be between 60 and 86400")
    enabled = _required_bool(value, "enabled")
    legal_approved = _required_bool(value, "legal_approved")
    requires_api_key = _required_bool(value, "requires_api_key")
    discovery_only = _required_bool(value, "discovery_only")
    automation_policy = _required_text(value, "automation_policy").lower()
    if automation_policy not in _AUTOMATION_POLICIES:
        raise ValueError("world source automation_policy is invalid")
    if enabled and not legal_approved:
        raise ValueError("enabled world sources must be legally approved")
    if enabled and automation_policy not in {"api", "feed", "approved_page"}:
        raise ValueError("world source automation policy does not allow enablement")

    return WorldSourceCatalogEntry(
        source_id=source_id,
        display_name=display_name,
        region=region,
        kind=kind,
        capabilities=capabilities,
        entry_url=entry_url,
        allowed_hosts=allowed_hosts,
        refresh_seconds=refresh_seconds,
        enabled=enabled,
        legal_approved=legal_approved,
        requires_api_key=requires_api_key,
        discovery_only=discovery_only,
        terms_url=terms_url,
        robots_url=robots_url,
        automation_policy=automation_policy,
    )


def _required_text(value: dict[str, object], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"world source {field} must be non-empty text")
    return result.strip()


def _required_bool(value: dict[str, object], field: str) -> bool:
    result = value.get(field)
    if not isinstance(result, bool):
        raise ValueError(f"world source {field} must be boolean")
    return result


def _host_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("world source allowed host must be non-empty text")
    return value.strip().lower()


def _optional_url(value: object, allowed_hosts: tuple[str, ...] | None) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError("world source URL must be text")
    return _validated_url(value.strip(), allowed_hosts)


def _validated_url(value: str, allowed_hosts: tuple[str, ...] | None) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("world source URLs must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("world source URLs must not contain credentials, query, or fragment")
    if allowed_hosts is not None and parsed.hostname.lower() not in allowed_hosts:
        raise ValueError("world source URL host is not allowlisted")
    return value
