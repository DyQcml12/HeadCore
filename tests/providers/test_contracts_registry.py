from __future__ import annotations

from collections import deque

import pytest

from app.providers import ProviderCapability, ProviderHealth, ProviderId, ProviderRegistry
from app.providers.fakes import FakeTextProvider


def test_provider_id_is_normalized_and_validated() -> None:
    assert ProviderId(" DeepSeek ").value == "deepseek"
    with pytest.raises(ValueError):
        ProviderId("two words")


def test_registry_rejects_duplicate_and_capability_mismatch() -> None:
    registry = ProviderRegistry()
    provider = FakeTextProvider(ProviderId("text-provider"), deque(["ok"]))
    registry.register(provider)

    assert registry.get("text-provider", ProviderCapability.TEXT) is provider
    with pytest.raises(ValueError):
        registry.get("text-provider", ProviderCapability.ASR)
    with pytest.raises(ValueError):
        registry.register(provider)


def test_registry_tracks_explicit_health() -> None:
    registry = ProviderRegistry()
    registry.register(FakeTextProvider(ProviderId("text-provider"), deque(["ok"])))

    registry.set_health("text-provider", ProviderHealth.DEGRADED)

    assert registry.health("text-provider") is ProviderHealth.DEGRADED

