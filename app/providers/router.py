from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from app.core.security import redact_secrets
from app.providers.contracts import (
    Provider,
    ProviderAttempt,
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderHealth,
    ProviderId,
    ProviderTrace,
    RoutingDecision,
)
from app.providers.registry import ProviderRegistry
from app.providers.runtime import ProviderRuntimeMonitor, provider_runtime_monitor


T = TypeVar("T")
Clock = Callable[[], float]
Invoker = Callable[[Provider], Awaitable[T]]
StreamInvoker = Callable[[Provider], AsyncIterator[str]]
_SENSITIVE_KEYS = {"authorization", "api_key", "apikey", "password", "secret", "token"}


@dataclass(frozen=True)
class RoutingPolicy:
    providers: tuple[ProviderId, ...]
    timeout_seconds: float = 30.0
    retries_per_provider: int = 0
    circuit_failure_threshold: int = 3
    circuit_recovery_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.providers:
            raise ValueError("routing policy requires at least one provider")
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be between 0 and 300")
        if not 0 <= self.retries_per_provider <= 5:
            raise ValueError("retries_per_provider must be between 0 and 5")
        if not 0 < self.circuit_failure_threshold <= 100:
            raise ValueError("invalid circuit breaker limits")
        if not 0 <= self.circuit_recovery_seconds <= 3600:
            raise ValueError("invalid circuit breaker limits")


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None


class RoutingFailed(ProviderError):
    def __init__(self, trace: ProviderTrace, last_error: ProviderError | None = None) -> None:
        code = trace.attempts[-1].error_code if trace.attempts else ProviderErrorCode.UNAVAILABLE
        super().__init__(code or ProviderErrorCode.UNAVAILABLE, "all configured providers failed")
        self.trace = trace
        self.last_error = _sanitize_error(last_error)


class StreamingRoutingFailed(RoutingFailed):
    def __init__(
        self,
        trace: ProviderTrace,
        last_error: ProviderError,
        *,
        partial_output: bool,
    ) -> None:
        super().__init__(trace, last_error)
        self.partial_output = partial_output


class StreamingRoutingDecision:
    def __init__(self, iterator: AsyncIterator[str], capability: ProviderCapability) -> None:
        self._iterator = iterator
        self.provider_id: ProviderId | None = None
        self.trace = ProviderTrace(capability, ())

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterator


class ProviderRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        clock: Clock = time.monotonic,
        monitor: ProviderRuntimeMonitor = provider_runtime_monitor,
    ) -> None:
        self._registry = registry
        self._clock = clock
        self._monitor = monitor
        self._circuits: dict[tuple[ProviderId, ProviderCapability], _CircuitState] = {}

    async def route(
        self,
        capability: ProviderCapability,
        policy: RoutingPolicy,
        invoke: Invoker[T],
    ) -> RoutingDecision[T]:
        attempts: list[ProviderAttempt] = []
        last_error: ProviderError | None = None
        for provider_id in policy.providers:
            state = self._circuits.setdefault((provider_id, capability), _CircuitState())
            if self._circuit_is_open(state, policy):
                attempts.append(self._skipped_attempt(provider_id, capability, ProviderErrorCode.UNAVAILABLE))
                self._publish(ProviderTrace(capability, tuple(attempts)))
                continue
            try:
                provider = self._registry.get(provider_id, capability)
            except KeyError:
                attempts.append(self._skipped_attempt(provider_id, capability, ProviderErrorCode.NOT_CONFIGURED))
                self._publish(ProviderTrace(capability, tuple(attempts)))
                continue
            except ValueError:
                attempts.append(self._skipped_attempt(provider_id, capability, ProviderErrorCode.INVALID_RESPONSE))
                self._publish(ProviderTrace(capability, tuple(attempts)))
                continue
            if self._registry.health(provider_id) is ProviderHealth.UNAVAILABLE:
                attempts.append(self._skipped_attempt(provider_id, capability, ProviderErrorCode.UNAVAILABLE))
                self._publish(ProviderTrace(capability, tuple(attempts)))
                continue

            for attempt_number in range(1, policy.retries_per_provider + 2):
                started_at = self._clock()
                try:
                    value = await asyncio.wait_for(invoke(provider), timeout=policy.timeout_seconds)
                except asyncio.TimeoutError:
                    error = ProviderError(ProviderErrorCode.TIMEOUT)
                except ProviderError as exc:
                    error = exc
                except Exception as exc:
                    error = ProviderError(
                        ProviderErrorCode.UNAVAILABLE,
                        details={"exception_type": type(exc).__name__},
                    )
                else:
                    state.failures = 0
                    state.opened_at = None
                    attempts.append(self._attempt(provider_id, capability, attempt_number, started_at, True))
                    trace = ProviderTrace(capability, tuple(attempts))
                    self._publish(trace)
                    return RoutingDecision(provider_id, value, trace)

                attempts.append(
                    self._attempt(
                        provider_id,
                        capability,
                        attempt_number,
                        started_at,
                        False,
                        error.code,
                        error.details,
                    )
                )
                last_error = error
                if error.code in {
                    ProviderErrorCode.UNAVAILABLE,
                    ProviderErrorCode.TIMEOUT,
                    ProviderErrorCode.INVALID_RESPONSE,
                    ProviderErrorCode.RATE_LIMITED,
                }:
                    self._record_failure(state, policy)
                self._publish(ProviderTrace(capability, tuple(attempts)))
                if state.opened_at is not None:
                    break
                if not error.retryable or attempt_number > policy.retries_per_provider:
                    break

        raise RoutingFailed(ProviderTrace(capability, tuple(attempts)), last_error)

    def stream(
        self,
        capability: ProviderCapability,
        policy: RoutingPolicy,
        invoke: StreamInvoker,
    ) -> StreamingRoutingDecision:
        decision = StreamingRoutingDecision(_empty_stream(), capability)
        decision._iterator = self._route_stream(decision, capability, policy, invoke)
        return decision

    async def _route_stream(
        self,
        decision: StreamingRoutingDecision,
        capability: ProviderCapability,
        policy: RoutingPolicy,
        invoke: StreamInvoker,
    ) -> AsyncIterator[str]:
        attempts: list[ProviderAttempt] = []
        last_error: ProviderError | None = None
        emitted_any = False
        for provider_id in policy.providers:
            state = self._circuits.setdefault((provider_id, capability), _CircuitState())
            provider, skipped_error = self._resolve_provider(provider_id, capability, state, policy)
            if skipped_error is not None:
                attempts.append(self._skipped_attempt(provider_id, capability, skipped_error))
                decision.trace = ProviderTrace(capability, tuple(attempts))
                self._publish(decision.trace)
                continue
            assert provider is not None
            for attempt_number in range(1, policy.retries_per_provider + 2):
                started_at = self._clock()
                emitted_this_attempt = False
                iterator: AsyncIterator[str] | None = None
                error: ProviderError | None = None
                try:
                    iterator = invoke(provider).__aiter__()
                    while True:
                        try:
                            chunk = await asyncio.wait_for(anext(iterator), timeout=policy.timeout_seconds)
                        except StopAsyncIteration:
                            break
                        if not isinstance(chunk, str) or not chunk:
                            continue
                        emitted_any = True
                        emitted_this_attempt = True
                        decision.provider_id = provider_id
                        yield chunk
                    if not emitted_this_attempt:
                        error = ProviderError(ProviderErrorCode.INVALID_RESPONSE, "provider stream was empty")
                except asyncio.TimeoutError:
                    error = ProviderError(ProviderErrorCode.TIMEOUT)
                except ProviderError as exc:
                    error = exc
                except Exception as exc:
                    error = ProviderError(
                        ProviderErrorCode.UNAVAILABLE,
                        details={"exception_type": type(exc).__name__},
                    )
                finally:
                    close = getattr(iterator, "aclose", None) if iterator is not None else None
                    if close is not None:
                        try:
                            await close()
                        except Exception as exc:
                            if error is None:
                                error = ProviderError(
                                    ProviderErrorCode.UNAVAILABLE,
                                    details={"exception_type": type(exc).__name__},
                                )
                            else:
                                error = ProviderError(
                                    error.code,
                                    retryable=error.retryable,
                                    details={
                                        **error.details,
                                        "close_exception_type": type(exc).__name__,
                                    },
                                )

                if error is None:
                    state.failures = 0
                    state.opened_at = None
                    attempts.append(self._attempt(provider_id, capability, attempt_number, started_at, True))
                    decision.trace = ProviderTrace(capability, tuple(attempts))
                    self._publish(decision.trace)
                    return

                attempts.append(
                    self._attempt(
                        provider_id,
                        capability,
                        attempt_number,
                        started_at,
                        False,
                        error.code,
                        error.details,
                    )
                )
                decision.trace = ProviderTrace(capability, tuple(attempts))
                last_error = error
                if error.code in {
                    ProviderErrorCode.UNAVAILABLE,
                    ProviderErrorCode.TIMEOUT,
                    ProviderErrorCode.INVALID_RESPONSE,
                    ProviderErrorCode.RATE_LIMITED,
                }:
                    self._record_failure(state, policy)
                self._publish(decision.trace)
                if emitted_any:
                    raise StreamingRoutingFailed(
                        decision.trace,
                        error,
                        partial_output=True,
                    )
                if state.opened_at is not None:
                    break
                if not error.retryable or attempt_number > policy.retries_per_provider:
                    break

        raise StreamingRoutingFailed(
            decision.trace,
            last_error or ProviderError(ProviderErrorCode.UNAVAILABLE),
            partial_output=False,
        )

    def _resolve_provider(
        self,
        provider_id: ProviderId,
        capability: ProviderCapability,
        state: _CircuitState,
        policy: RoutingPolicy,
    ) -> tuple[Provider | None, ProviderErrorCode | None]:
        if self._circuit_is_open(state, policy):
            return None, ProviderErrorCode.UNAVAILABLE
        try:
            provider = self._registry.get(provider_id, capability)
        except KeyError:
            return None, ProviderErrorCode.NOT_CONFIGURED
        except ValueError:
            return None, ProviderErrorCode.INVALID_RESPONSE
        if self._registry.health(provider_id) is ProviderHealth.UNAVAILABLE:
            return None, ProviderErrorCode.UNAVAILABLE
        return provider, None

    def _circuit_is_open(self, state: _CircuitState, policy: RoutingPolicy) -> bool:
        if state.opened_at is None:
            return False
        if self._clock() - state.opened_at >= policy.circuit_recovery_seconds:
            state.opened_at = None
            state.failures = 0
            return False
        return True

    def _record_failure(self, state: _CircuitState, policy: RoutingPolicy) -> None:
        state.failures += 1
        if state.failures >= policy.circuit_failure_threshold:
            state.opened_at = self._clock()

    def _attempt(
        self,
        provider_id: ProviderId,
        capability: ProviderCapability,
        number: int,
        started_at: float,
        success: bool,
        error_code: ProviderErrorCode | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> ProviderAttempt:
        return ProviderAttempt(
            provider_id=provider_id,
            capability=capability,
            attempt=number,
            started_at=started_at,
            duration_seconds=max(0.0, self._clock() - started_at),
            success=success,
            error_code=error_code,
            details=_redact(details or {}),
        )

    def _skipped_attempt(
        self,
        provider_id: ProviderId,
        capability: ProviderCapability,
        error_code: ProviderErrorCode,
    ) -> ProviderAttempt:
        return ProviderAttempt(provider_id, capability, 0, self._clock(), 0.0, False, error_code)

    def _publish(self, trace: ProviderTrace) -> None:
        if not trace.attempts:
            return
        attempt = trace.attempts[-1]
        state = self._circuits.get((attempt.provider_id, trace.capability), _CircuitState())
        self._monitor.record(
            trace,
            failure_count=state.failures,
            circuit_open=state.opened_at is not None,
        )


def _redact(value: Any, *, key: str = "") -> Any:
    if any(marker in key.lower() for marker in _SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): _redact(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact(item) for item in value]
    return value


def _sanitize_error(error: ProviderError | None) -> ProviderError | None:
    if error is None:
        return None
    return ProviderError(
        error.code,
        redact_secrets(str(error)),
        retryable=error.retryable,
        details=_redact(error.details),
    )


async def _empty_stream() -> AsyncIterator[str]:
    if False:
        yield ""
