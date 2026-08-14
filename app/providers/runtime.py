from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from app.providers.contracts import ProviderCapability, ProviderErrorCode, ProviderHealth, ProviderId, ProviderTrace


@dataclass(frozen=True)
class ProviderRuntimeStatus:
    provider_id: ProviderId
    capability: ProviderCapability
    health: ProviderHealth
    failure_count: int
    circuit_open: bool
    last_error_code: ProviderErrorCode | None
    checked_at: datetime


class ProviderRuntimeMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._statuses: dict[tuple[ProviderId, ProviderCapability], ProviderRuntimeStatus] = {}

    def record(self, trace: ProviderTrace, *, failure_count: int, circuit_open: bool) -> None:
        if not trace.attempts:
            return
        attempt = trace.attempts[-1]
        health = ProviderHealth.HEALTHY if attempt.success else ProviderHealth.DEGRADED
        if circuit_open:
            health = ProviderHealth.CIRCUIT_OPEN
        status = ProviderRuntimeStatus(
            provider_id=attempt.provider_id,
            capability=trace.capability,
            health=health,
            failure_count=failure_count,
            circuit_open=circuit_open,
            last_error_code=attempt.error_code,
            checked_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._statuses[(attempt.provider_id, trace.capability)] = status

    def snapshot(self) -> tuple[ProviderRuntimeStatus, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._statuses.values(),
                    key=lambda item: (item.capability.value, item.provider_id.value),
                )
            )

    def clear(self) -> None:
        with self._lock:
            self._statuses.clear()


provider_runtime_monitor = ProviderRuntimeMonitor()
