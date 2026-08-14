from __future__ import annotations

from typing import Protocol

from app.operations.contracts import ComponentStatus


class StatusProvider(Protocol):
    @property
    def component_id(self) -> str:
        """Return the stable component identifier."""
        ...

    async def get_status(self) -> ComponentStatus:
        """Run a cheap, side-effect-free readiness check."""
        ...

