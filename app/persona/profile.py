from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaGatePolicy:
    forbidden_identity_markers: tuple[str, ...]
    assistant_template_markers: tuple[str, ...]


@dataclass(frozen=True)
class PersonaProfile:
    id: str
    version: int
    aliases: tuple[str, ...]
    identity_name: str
    default_style: str
    core_lines: tuple[str, ...]
    gate_policy: PersonaGatePolicy


@dataclass(frozen=True)
class PersonaResolution:
    requested_id: str
    profile: PersonaProfile
    fallback_used: bool
    reason: str
