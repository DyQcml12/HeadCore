from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Iterable

from app.operations.contracts import ComponentState, ComponentStatus, OperationsSnapshot
from app.operations.providers import StatusProvider


_UNHEALTHY = {
    ComponentState.OFFLINE,
    ComponentState.DEGRADED,
    ComponentState.MISSING,
    ComponentState.NOT_CONFIGURED,
}


class OperationsStatusService:
    def __init__(self, providers: Iterable[StatusProvider], *, timeout_seconds: float = 1.0) -> None:
        self._providers = tuple(providers)
        self._timeout_seconds = timeout_seconds

    async def snapshot(self) -> OperationsSnapshot:
        statuses = await asyncio.gather(*(self._check(provider) for provider in self._providers))
        components = {status.component_id: status for status in statuses}
        components = {
            component_id: self._propagate_dependencies(status, components)
            for component_id, status in components.items()
        }
        overall = ComponentState.ONLINE
        if any(status.state in _UNHEALTHY for status in components.values()):
            overall = ComponentState.DEGRADED
        return OperationsSnapshot(
            state=overall,
            components=components,
            generated_at=datetime.now(timezone.utc),
        )

    async def _check(self, provider: StatusProvider) -> ComponentStatus:
        try:
            return await asyncio.wait_for(provider.get_status(), timeout=self._timeout_seconds)
        except TimeoutError:
            detail = f"status check timed out after {self._timeout_seconds:g}s"
        except Exception as exc:
            detail = f"status check failed: {type(exc).__name__}"
        return ComponentStatus(
            component_id=provider.component_id,
            label=provider.component_id,
            category="unknown",
            state=ComponentState.DEGRADED,
            detail=detail,
        )

    @staticmethod
    def _propagate_dependencies(
        status: ComponentStatus,
        components: dict[str, ComponentStatus],
    ) -> ComponentStatus:
        blocked = [
            dependency.component_id
            for dependency in status.dependencies
            if dependency.state in _UNHEALTHY
            or (
                dependency.component_id in components
                and components[dependency.component_id].state in _UNHEALTHY
            )
        ]
        if not blocked or status.state is not ComponentState.ONLINE:
            return status
        return ComponentStatus(
            component_id=status.component_id,
            label=status.label,
            category=status.category,
            state=ComponentState.DEGRADED,
            detail=f"blocked by: {', '.join(blocked)}",
            dependencies=status.dependencies,
            checked_at=status.checked_at,
        )
