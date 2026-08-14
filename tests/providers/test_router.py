from __future__ import annotations

import asyncio
from collections import deque

import pytest

from app.providers import (
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderId,
    ProviderRegistry,
    ProviderRouter,
    RoutingFailed,
    RoutingPolicy,
    TextRequest,
)
from app.providers.fakes import FakeClock, FakeProvider, FakeTextProvider


REQUEST = TextRequest("system", "user")


def policy(*names: str, retries: int = 0, threshold: int = 3, recovery: float = 60) -> RoutingPolicy:
    return RoutingPolicy(
        tuple(ProviderId(name) for name in names),
        timeout_seconds=0.01,
        retries_per_provider=retries,
        circuit_failure_threshold=threshold,
        circuit_recovery_seconds=recovery,
    )


def test_routes_to_first_successful_provider_in_controlled_order() -> None:
    registry = ProviderRegistry()
    first = FakeTextProvider(
        ProviderId("first"),
        deque([ProviderError(ProviderErrorCode.MODEL_MISSING)]),
    )
    second = FakeTextProvider(ProviderId("second"), deque(["answer"]))
    registry.register(first)
    registry.register(second)

    decision = asyncio.run(
        ProviderRouter(registry).route(
            ProviderCapability.TEXT,
            policy("first", "missing", "second"),
            lambda provider: provider.generate_text(REQUEST),
        )
    )

    assert decision.provider_id == ProviderId("second")
    assert decision.value == "answer"
    assert [attempt.provider_id.value for attempt in decision.trace.attempts] == ["first", "missing", "second"]
    assert decision.trace.attempts[1].error_code is ProviderErrorCode.NOT_CONFIGURED


def test_capability_mismatch_never_invokes_provider() -> None:
    registry = ProviderRegistry()
    provider = FakeProvider(ProviderId("asr-only"), frozenset({ProviderCapability.ASR}))
    registry.register(provider)
    invoked = False

    async def invoke(_provider: object) -> str:
        nonlocal invoked
        invoked = True
        return "unexpected"

    with pytest.raises(RoutingFailed) as caught:
        asyncio.run(ProviderRouter(registry).route(ProviderCapability.TEXT, policy("asr-only"), invoke))

    assert invoked is False
    assert caught.value.trace.attempts[0].error_code is ProviderErrorCode.INVALID_RESPONSE


def test_retryable_error_retries_but_authentication_failure_does_not() -> None:
    registry = ProviderRegistry()
    retrying = FakeTextProvider(
        ProviderId("retrying"),
        deque([ProviderError(ProviderErrorCode.RATE_LIMITED), "ok"]),
    )
    auth = FakeTextProvider(
        ProviderId("auth"),
        deque([ProviderError(ProviderErrorCode.AUTHENTICATION_FAILED), "must-not-run"]),
    )
    registry.register(retrying)
    registry.register(auth)
    router = ProviderRouter(registry)

    decision = asyncio.run(
        router.route(
            ProviderCapability.TEXT,
            policy("retrying", retries=1),
            lambda provider: provider.generate_text(REQUEST),
        )
    )
    assert decision.value == "ok"
    assert len(retrying.calls) == 2

    with pytest.raises(RoutingFailed):
        asyncio.run(
            router.route(
                ProviderCapability.TEXT,
                policy("auth", retries=2),
                lambda provider: provider.generate_text(REQUEST),
            )
        )
    assert len(auth.calls) == 1


def test_authentication_failure_does_not_open_circuit() -> None:
    registry = ProviderRegistry()
    provider = FakeTextProvider(
        ProviderId("auth"),
        deque(
            [
                ProviderError(ProviderErrorCode.AUTHENTICATION_FAILED),
                ProviderError(ProviderErrorCode.AUTHENTICATION_FAILED),
            ]
        ),
    )
    registry.register(provider)
    router = ProviderRouter(registry)
    route_policy = policy("auth", threshold=1)

    for _ in range(2):
        with pytest.raises(RoutingFailed):
            asyncio.run(
                router.route(
                    ProviderCapability.TEXT,
                    route_policy,
                    lambda item: item.generate_text(REQUEST),
                )
            )

    assert len(provider.calls) == 2


def test_routing_policy_enforces_operational_limits() -> None:
    with pytest.raises(ValueError):
        policy("provider", retries=6)
    with pytest.raises(ValueError):
        RoutingPolicy((ProviderId("provider"),), timeout_seconds=301)


def test_timeout_falls_back() -> None:
    registry = ProviderRegistry()
    slow = FakeTextProvider(ProviderId("slow"), deque(["unused"]))
    fallback = FakeTextProvider(ProviderId("fallback"), deque(["ok"]))
    registry.register(slow)
    registry.register(fallback)

    async def invoke(provider: FakeTextProvider) -> str:
        if provider is slow:
            await asyncio.sleep(0.1)
        return await provider.generate_text(REQUEST)

    decision = asyncio.run(
        ProviderRouter(registry).route(
            ProviderCapability.TEXT,
            policy("slow", "fallback"),
            invoke,
        )
    )

    assert decision.value == "ok"
    assert decision.trace.attempts[0].error_code is ProviderErrorCode.TIMEOUT


def test_circuit_opens_and_recovers_with_fake_clock() -> None:
    clock = FakeClock()
    registry = ProviderRegistry()
    provider = FakeTextProvider(
        ProviderId("unstable"),
        deque([ProviderError(ProviderErrorCode.UNAVAILABLE), "recovered"]),
    )
    registry.register(provider)
    router = ProviderRouter(registry, clock=clock)
    route_policy = policy("unstable", threshold=1, recovery=10)

    with pytest.raises(RoutingFailed):
        asyncio.run(
            router.route(
                ProviderCapability.TEXT,
                route_policy,
                lambda item: item.generate_text(REQUEST),
            )
        )
    with pytest.raises(RoutingFailed) as open_circuit:
        asyncio.run(
            router.route(
                ProviderCapability.TEXT,
                route_policy,
                lambda item: item.generate_text(REQUEST),
            )
        )
    assert open_circuit.value.trace.attempts[0].attempt == 0
    assert len(provider.calls) == 1

    clock.advance(10)
    decision = asyncio.run(
        router.route(
            ProviderCapability.TEXT,
            route_policy,
            lambda item: item.generate_text(REQUEST),
        )
    )
    assert decision.value == "recovered"
    assert len(provider.calls) == 2


def test_trace_redacts_nested_sensitive_details() -> None:
    registry = ProviderRegistry()
    provider = FakeTextProvider(
        ProviderId("secretive"),
        deque(
            [
                ProviderError(
                    ProviderErrorCode.INVALID_RESPONSE,
                    details={
                        "api_key": "private-value",
                        "headers": {"Authorization": "Bearer private-value", "request_id": "safe-id"},
                    },
                )
            ]
        ),
    )
    registry.register(provider)

    with pytest.raises(RoutingFailed) as caught:
        asyncio.run(
            ProviderRouter(registry).route(
                ProviderCapability.TEXT,
                policy("secretive"),
                lambda item: item.generate_text(REQUEST),
            )
        )

    details = caught.value.trace.attempts[0].details
    assert details["api_key"] == "[REDACTED]"
    assert details["headers"]["Authorization"] == "[REDACTED]"
    assert details["headers"]["request_id"] == "safe-id"
    assert "private-value" not in repr(caught.value.trace)
    assert caught.value.last_error is not None
    assert caught.value.last_error.details["api_key"] == "[REDACTED]"
    assert "private-value" not in str(caught.value.last_error)


def test_open_circuit_stops_remaining_retries_for_same_provider() -> None:
    registry = ProviderRegistry()
    provider = FakeTextProvider(
        ProviderId("unstable"),
        deque(
            [
                ProviderError(ProviderErrorCode.UNAVAILABLE),
                "must-not-run-after-open",
            ]
        ),
    )
    fallback = FakeTextProvider(ProviderId("fallback"), deque(["ok"]))
    registry.register(provider)
    registry.register(fallback)

    decision = asyncio.run(
        ProviderRouter(registry).route(
            ProviderCapability.TEXT,
            policy("unstable", "fallback", retries=2, threshold=1),
            lambda item: item.generate_text(REQUEST),
        )
    )

    assert decision.value == "ok"
    assert len(provider.calls) == 1
