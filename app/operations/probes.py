from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.operations.contracts import ComponentState, ComponentStatus, DependencyStatus


@dataclass(frozen=True)
class StaticStatusProvider:
    component_id: str
    label: str
    category: str
    configured: bool
    ready: bool
    detail: str = ""
    dependencies: tuple[DependencyStatus, ...] = ()

    async def get_status(self) -> ComponentStatus:
        state = ComponentState.NOT_CONFIGURED
        if self.configured:
            state = ComponentState.ONLINE if self.ready else ComponentState.DEGRADED
        return ComponentStatus(
            component_id=self.component_id,
            label=self.label,
            category=self.category,
            state=state,
            detail=self.detail,
            dependencies=self.dependencies,
        )


@dataclass(frozen=True)
class TcpStatusProvider:
    component_id: str
    label: str
    host: str
    port: int
    category: str = "service"
    connect_timeout: float = 0.5

    async def get_status(self) -> ComponentStatus:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.connect_timeout,
            )
        except (OSError, TimeoutError):
            state = ComponentState.OFFLINE
        else:
            state = ComponentState.ONLINE
            writer.close()
            await writer.wait_closed()
        return ComponentStatus(
            component_id=self.component_id,
            label=self.label,
            category=self.category,
            state=state,
        )


@dataclass(frozen=True)
class HttpStatusProvider:
    component_id: str
    label: str
    url: str
    category: str = "service"
    request_timeout: float = 0.5

    async def get_status(self) -> ComponentStatus:
        state = await asyncio.to_thread(self._check)
        return ComponentStatus(
            component_id=self.component_id,
            label=self.label,
            category=self.category,
            state=state,
        )

    def _check(self) -> ComponentState:
        request = urllib.request.Request(self.url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                return ComponentState.ONLINE if response.status < 500 else ComponentState.DEGRADED
        except urllib.error.HTTPError as exc:
            return ComponentState.DEGRADED if exc.code < 500 else ComponentState.OFFLINE
        except (urllib.error.URLError, TimeoutError, OSError):
            return ComponentState.OFFLINE
