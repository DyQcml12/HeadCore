from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from app.providers import (
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderId,
    ProviderRegistry,
    ProviderRouter,
    RoutingPolicy,
    StreamingRoutingFailed,
)


@dataclass
class StreamProvider:
    provider_id: ProviderId
    events: list[str | Exception]
    delay_seconds: float = 0.0
    capabilities: frozenset[ProviderCapability] = field(
        default_factory=lambda: frozenset({ProviderCapability.TEXT})
    )
    calls: int = 0

    async def stream(self):
        self.calls += 1
        for event in self.events:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            if isinstance(event, Exception):
                raise event
            yield event


async def collect(route) -> str:
    chunks = []
    async for chunk in route:
        chunks.append(chunk)
    return "".join(chunks)


def make_policy(*names: str, timeout: float = 0.05) -> RoutingPolicy:
    return RoutingPolicy(tuple(ProviderId(name) for name in names), timeout_seconds=timeout)


def test_stream_falls_back_before_first_chunk() -> None:
    registry = ProviderRegistry()
    first = StreamProvider(ProviderId("first"), [ProviderError(ProviderErrorCode.UNAVAILABLE)])
    second = StreamProvider(ProviderId("second"), ["ok"])
    registry.register(first)
    registry.register(second)
    route = ProviderRouter(registry).stream(
        ProviderCapability.TEXT,
        make_policy("first", "second"),
        lambda provider: provider.stream(),
    )

    assert asyncio.run(collect(route)) == "ok"
    assert route.provider_id == ProviderId("second")
    assert [attempt.success for attempt in route.trace.attempts] == [False, True]


def test_empty_stream_falls_back_as_invalid_response() -> None:
    registry = ProviderRegistry()
    registry.register(StreamProvider(ProviderId("empty"), []))
    registry.register(StreamProvider(ProviderId("second"), ["ok"]))
    route = ProviderRouter(registry).stream(
        ProviderCapability.TEXT,
        make_policy("empty", "second"),
        lambda provider: provider.stream(),
    )

    assert asyncio.run(collect(route)) == "ok"
    assert route.trace.attempts[0].error_code is ProviderErrorCode.INVALID_RESPONSE


def test_partial_stream_failure_never_switches_provider() -> None:
    registry = ProviderRegistry()
    first = StreamProvider(ProviderId("first"), ["partial", RuntimeError("broken")])
    second = StreamProvider(ProviderId("second"), ["duplicate"])
    registry.register(first)
    registry.register(second)
    route = ProviderRouter(registry).stream(
        ProviderCapability.TEXT,
        make_policy("first", "second"),
        lambda provider: provider.stream(),
    )

    async def consume() -> list[str]:
        chunks = []
        with pytest.raises(StreamingRoutingFailed) as caught:
            async for chunk in route:
                chunks.append(chunk)
        assert caught.value.partial_output is True
        return chunks

    assert asyncio.run(consume()) == ["partial"]
    assert second.calls == 0


def test_stream_chunk_timeout_is_traced() -> None:
    registry = ProviderRegistry()
    registry.register(StreamProvider(ProviderId("slow"), ["late"], delay_seconds=0.05))
    route = ProviderRouter(registry).stream(
        ProviderCapability.TEXT,
        make_policy("slow", timeout=0.01),
        lambda provider: provider.stream(),
    )

    with pytest.raises(StreamingRoutingFailed) as caught:
        asyncio.run(collect(route))

    assert caught.value.partial_output is False
    assert route.trace.attempts[0].error_code is ProviderErrorCode.TIMEOUT


def test_missing_stream_implementation_falls_back_with_trace() -> None:
    registry = ProviderRegistry()
    incomplete = StreamProvider(ProviderId("incomplete"), ["unused"])
    fallback = StreamProvider(ProviderId("fallback"), ["ok"])
    registry.register(incomplete)
    registry.register(fallback)
    route = ProviderRouter(registry).stream(
        ProviderCapability.TEXT,
        make_policy("incomplete", "fallback"),
        lambda provider: provider.stream() if provider is fallback else provider.missing_stream(),
    )

    assert asyncio.run(collect(route)) == "ok"
    assert route.trace.attempts[0].error_code is ProviderErrorCode.UNAVAILABLE
    assert route.trace.attempts[1].success is True


def test_stream_close_failure_is_traced_and_falls_back_before_output() -> None:
    class CloseFailingIterator:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self) -> None:
            raise RuntimeError("close failed")

    registry = ProviderRegistry()
    first = StreamProvider(ProviderId("first"), [])
    second = StreamProvider(ProviderId("second"), ["ok"])
    registry.register(first)
    registry.register(second)
    route = ProviderRouter(registry).stream(
        ProviderCapability.TEXT,
        make_policy("first", "second"),
        lambda provider: CloseFailingIterator() if provider is first else provider.stream(),
    )

    assert asyncio.run(collect(route)) == "ok"
    assert route.trace.attempts[0].error_code is ProviderErrorCode.INVALID_RESPONSE
    assert route.trace.attempts[0].details == {"close_exception_type": "RuntimeError"}
