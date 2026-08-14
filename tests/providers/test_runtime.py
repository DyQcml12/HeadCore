from __future__ import annotations

import asyncio
from collections import deque

import pytest

from app.operations.contracts import ComponentState
from app.operations.project_status import ProviderRuntimeStatusProvider
from app.providers import ProviderCapability, ProviderError, ProviderErrorCode, ProviderId, ProviderRegistry
from app.providers import ProviderRouter, RoutingFailed, RoutingPolicy, TextRequest
from app.providers.fakes import FakeTextProvider
from app.providers.runtime import ProviderRuntimeMonitor


def _failed_monitor(code: ProviderErrorCode) -> ProviderRuntimeMonitor:
    monitor = ProviderRuntimeMonitor()
    registry = ProviderRegistry()
    provider = FakeTextProvider(ProviderId("runtime-test"), deque([ProviderError(code, "token=private")]))
    registry.register(provider)
    with pytest.raises(RoutingFailed):
        asyncio.run(
            ProviderRouter(registry, monitor=monitor).route(
                ProviderCapability.TEXT,
                RoutingPolicy((provider.provider_id,)),
                lambda item: item.generate_text(TextRequest("system", "user")),
            )
        )
    return monitor


def test_router_publishes_non_sensitive_runtime_status() -> None:
    status = _failed_monitor(ProviderErrorCode.RATE_LIMITED).snapshot()[0]
    assert status.last_error_code is ProviderErrorCode.RATE_LIMITED
    assert status.failure_count == 1
    assert "private" not in repr(status)


def test_operations_runtime_status_exposes_counts_and_codes_only() -> None:
    result = asyncio.run(
        ProviderRuntimeStatusProvider(_failed_monitor(ProviderErrorCode.MODEL_MISSING)).get_status()
    )
    assert result.state is ComponentState.DEGRADED
    assert result.detail == "tracked=1; degraded=1; open_circuits=0; error_codes=model_missing"
    assert "runtime-test" not in result.detail
