from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.providers.contracts import ProviderCapability, ProviderError, ProviderId, TextRequest


@dataclass
class FakeClock:
    current: float = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("fake clock cannot move backwards")
        self.current += seconds


@dataclass
class FakeTextProvider:
    provider_id: ProviderId
    outcomes: deque[str | ProviderError]
    capabilities: frozenset[ProviderCapability] = field(
        default_factory=lambda: frozenset({ProviderCapability.TEXT})
    )
    calls: list[TextRequest] = field(default_factory=list)

    async def generate_text(self, request: TextRequest) -> str:
        self.calls.append(request)
        if not self.outcomes:
            raise AssertionError("fake provider has no configured outcome")
        outcome = self.outcomes.popleft()
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


@dataclass
class FakeProvider:
    provider_id: ProviderId
    capabilities: frozenset[ProviderCapability]
    outcome: Any = None

