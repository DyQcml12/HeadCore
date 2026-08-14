from __future__ import annotations

import json

from app.persona_management.contracts import PersonaDefinition
from app.persona_management.service import PersonaManagementError


def encode_definition(definition: PersonaDefinition) -> str:
    return json.dumps(
        {
            "profile_id": definition.profile_id,
            "aliases": list(definition.aliases),
            "default_style": definition.default_style,
            "core_lines": list(definition.core_lines),
            "enabled_gates": sorted(definition.enabled_gates),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_definition(value: str) -> PersonaDefinition:
    try:
        data = json.loads(value)
        if not isinstance(data, dict):
            raise TypeError
        profile_id = _string(data, "profile_id")
        aliases = _string_tuple(data, "aliases")
        default_style = _string(data, "default_style")
        core_lines = _string_tuple(data, "core_lines")
        enabled_gates = frozenset(_string_tuple(data, "enabled_gates"))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PersonaManagementError("invalid_persisted_persona_definition") from exc
    return PersonaDefinition(
        profile_id=profile_id,
        aliases=aliases,
        default_style=default_style,
        core_lines=core_lines,
        enabled_gates=enabled_gates,
    )


def encode_surface(surface: tuple[tuple[str, str], ...]) -> str:
    return json.dumps(dict(surface), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def decode_surface(value: str) -> tuple[tuple[str, str], ...]:
    try:
        data = json.loads(value)
        if not isinstance(data, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in data.items()
        ):
            raise TypeError
    except (json.JSONDecodeError, TypeError) as exc:
        raise PersonaManagementError("invalid_persisted_persona_surface") from exc
    return tuple(sorted(data.items()))


def _string(data: dict[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _string_tuple(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError
    return tuple(value)

