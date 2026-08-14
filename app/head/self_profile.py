from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SELF_PROFILE_MEMORY_TYPE = "head_self_profile"
SELF_PROFILE_SESSION_ID = "head-self-profile"

_MAX_IDENTITY_SUMMARY_CHARS = 120
_MAX_LIST_ITEMS_VALUES = 5
_MAX_LIST_ITEMS_CAPABILITIES = 3
_MAX_LIST_ITEM_CHARS = 60
_SCALAR_FIELDS = (
    "identity_summary",
    "updated_at",
    "last_session_at",
)
_LIST_FIELDS = ("values", "boundaries", "capabilities_known", "uncertainties_known")


@dataclass(frozen=True)
class SelfProfile:
    schema_version: int = 1
    revision: int = 1
    updated_at: str = ""
    last_session_at: str | None = None
    identity_summary: str = ""
    values: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()
    capabilities_known: tuple[str, ...] = ()
    uncertainties_known: tuple[str, ...] = ()
    source_stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "last_session_at": self.last_session_at,
            "identity_summary": self.identity_summary,
            "values": list(self.values),
            "boundaries": list(self.boundaries),
            "capabilities_known": list(self.capabilities_known),
            "uncertainties_known": list(self.uncertainties_known),
            "source_stats": dict(self.source_stats),
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checked_text(value: object, field_name: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"self profile {field_name} must be text")
    text = value.strip()
    if len(text) > max_chars:
        raise ValueError(
            f"self profile {field_name} exceeds {max_chars} characters"
        )
    return text


def _checked_list(value: object, field_name: str, max_items: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"self profile {field_name} must be a list")
    items = tuple(
        _checked_text(item, field_name, _MAX_LIST_ITEM_CHARS) for item in value
    )
    items = tuple(item for item in items if item)
    if len(items) > max_items:
        raise ValueError(
            f"self profile {field_name} allows at most {max_items} items"
        )
    return items


def _checked_stats(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("self profile source_stats must be an object")
    stats: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, int) or item < 0:
            raise ValueError("self profile source_stats values must be non-negative ints")
        stats[key] = item
    if len(stats) > 16:
        raise ValueError("self profile source_stats allows at most 16 keys")
    return stats


def sanitize_self_profile(raw: object) -> SelfProfile:
    """Build a validated SelfProfile from untrusted input.

    Only whitelisted fields survive. Any type or length violation raises
    ValueError so callers must reject the write instead of guessing.
    """
    if not isinstance(raw, dict):
        raise ValueError("self profile payload must be an object")
    schema_version = raw.get("schema_version", 1)
    if not isinstance(schema_version, int) or schema_version != 1:
        raise ValueError("self profile schema_version must be 1")
    revision = raw.get("revision", 1)
    if not isinstance(revision, int) or revision < 1:
        raise ValueError("self profile revision must be a positive int")
    updated_at = _checked_text(raw.get("updated_at", ""), "updated_at", 64)
    last_session_at = raw.get("last_session_at")
    if last_session_at is not None:
        last_session_at = _checked_text(last_session_at, "last_session_at", 64)
    return SelfProfile(
        schema_version=schema_version,
        revision=revision,
        updated_at=updated_at,
        last_session_at=last_session_at,
        identity_summary=_checked_text(
            raw.get("identity_summary", ""),
            "identity_summary",
            _MAX_IDENTITY_SUMMARY_CHARS,
        ),
        values=_checked_list(raw.get("values", []), "values", _MAX_LIST_ITEMS_VALUES),
        boundaries=_checked_list(
            raw.get("boundaries", []),
            "boundaries",
            _MAX_LIST_ITEMS_VALUES,
        ),
        capabilities_known=_checked_list(
            raw.get("capabilities_known", []),
            "capabilities_known",
            _MAX_LIST_ITEMS_CAPABILITIES,
        ),
        uncertainties_known=_checked_list(
            raw.get("uncertainties_known", []),
            "uncertainties_known",
            _MAX_LIST_ITEMS_CAPABILITIES,
        ),
        source_stats=_checked_stats(raw.get("source_stats", {})),
    )


def self_profile_to_json(profile: SelfProfile) -> str:
    return json.dumps(profile.to_dict(), ensure_ascii=False)


def self_profile_from_json(text: str) -> SelfProfile | None:
    """Parse persisted profile text; corrupted or invalid content yields None.

    A corrupted profile must never crash the conversation path: callers fall
    back to the static persona registry when this returns None.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    try:
        return sanitize_self_profile(data)
    except ValueError:
        return None


def render_self_profile_projection(
    profile: SelfProfile | None,
    *,
    now: str | None = None,
) -> str:
    """Render the internal cross-session self projection.

    Returns an empty string when no profile exists so the prompt path stays
    byte-identical to today's behavior. The projection is internal
    consistency material only: it must not be repeated to the user and must
    not claim real consciousness.
    """
    if profile is None:
        return ""
    lines = ["[内部自我档案投影：仅用于跨会话一致性，不向用户复述，不宣称意识]"]
    if profile.identity_summary:
        lines.append(f"身份一致性要点：{profile.identity_summary}")
    if profile.values:
        lines.append("坚持的表达方式：" + "；".join(profile.values))
    if profile.boundaries:
        lines.append("长期边界：" + "；".join(profile.boundaries))
    if profile.capabilities_known:
        lines.append("已知能力：" + "；".join(profile.capabilities_known))
    if profile.uncertainties_known:
        lines.append("已知不确定性：" + "；".join(profile.uncertainties_known))
    if profile.last_session_at:
        try:
            last = datetime.fromisoformat(profile.last_session_at)
            current = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            delta = current - last
            days = max(0, int(delta.total_seconds() // 86400))
            hours = max(0, int(delta.total_seconds() % 86400 // 3600))
            lines.append(f"上次对话：约 {days} 天 {hours} 小时前")
        except ValueError:
            lines.append(f"上次对话：{profile.last_session_at}")
    return "\n".join(lines)
