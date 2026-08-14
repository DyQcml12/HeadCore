from __future__ import annotations

from dataclasses import dataclass

from app.providers.contracts import Provider, ProviderCapability, ProviderHealth, ProviderId


@dataclass
class ProviderRegistration:
    provider: Provider
    health: ProviderHealth = ProviderHealth.HEALTHY


class ProviderRegistry:
    def __init__(self) -> None:
        self._registrations: dict[ProviderId, ProviderRegistration] = {}

    def register(self, provider: Provider) -> None:
        if provider.provider_id in self._registrations:
            raise ValueError(f"provider already registered: {provider.provider_id}")
        if not provider.capabilities:
            raise ValueError("provider must declare at least one capability")
        self._registrations[provider.provider_id] = ProviderRegistration(provider=provider)

    def get(self, provider_id: ProviderId | str, capability: ProviderCapability) -> Provider:
        normalized_id = provider_id if isinstance(provider_id, ProviderId) else ProviderId(provider_id)
        registration = self._registrations.get(normalized_id)
        if registration is None:
            raise KeyError(str(normalized_id))
        if capability not in registration.provider.capabilities:
            raise ValueError(f"provider {normalized_id} does not support {capability.value}")
        return registration.provider

    def health(self, provider_id: ProviderId | str) -> ProviderHealth:
        normalized_id = provider_id if isinstance(provider_id, ProviderId) else ProviderId(provider_id)
        registration = self._registrations.get(normalized_id)
        if registration is None:
            raise KeyError(str(normalized_id))
        return registration.health

    def set_health(self, provider_id: ProviderId | str, health: ProviderHealth) -> None:
        normalized_id = provider_id if isinstance(provider_id, ProviderId) else ProviderId(provider_id)
        registration = self._registrations.get(normalized_id)
        if registration is None:
            raise KeyError(str(normalized_id))
        registration.health = health

