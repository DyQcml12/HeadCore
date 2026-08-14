from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class PlatformPersonaSelection:
    profile_id: str
    display_name: str
    style: str


def select_platform_persona(
    settings: Settings,
    platform: str | None,
) -> PlatformPersonaSelection:
    del platform
    return PlatformPersonaSelection(
        profile_id=settings.persona_profile,
        display_name=settings.persona_display_name,
        style=settings.persona_style,
    )
