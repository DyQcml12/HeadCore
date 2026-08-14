from __future__ import annotations

from collections.abc import Callable

from app.channels import capabilities_for
from app.channels.contracts import ChannelPlatform
from app.operations.contracts import ComponentState, ComponentStatus
from app.persona_management.contracts import PersonaManagementStatus
from app.providers.contracts import ProviderHealth, ProviderId
from app.providers.registry import ProviderRegistry


class ChannelContractStatusProvider:
    component_id = "channel_contracts"

    async def get_status(self) -> ComponentStatus:
        core_api = capabilities_for(ChannelPlatform.CORE_API)
        ready = core_api.text
        return ComponentStatus(
            component_id=self.component_id,
            label="Channel capabilities",
            category="channel",
            state=ComponentState.ONLINE if ready else ComponentState.DEGRADED,
            detail=f"Core API text={core_api.text}",
        )


class PersonaManagementStatusProvider:
    component_id = "persona_management"

    def __init__(self, get_status: Callable[[], PersonaManagementStatus]) -> None:
        self._get_status = get_status

    async def get_status(self) -> ComponentStatus:
        status = self._get_status()
        state = ComponentState.ONLINE if status.durable and status.write_ready else ComponentState.DEGRADED
        return ComponentStatus(
            component_id=self.component_id,
            label="Persona management",
            category="persona",
            state=state,
            detail=f"backend={status.storage_backend}; active_profiles={len(status.active_profiles)}",
        )


class ProviderRegistryStatusProvider:
    def __init__(self, registry: ProviderRegistry, provider_id: ProviderId | str) -> None:
        self._registry = registry
        self._provider_id = ProviderId(provider_id) if isinstance(provider_id, str) else provider_id
        self.component_id = f"provider_{self._provider_id.value}"

    async def get_status(self) -> ComponentStatus:
        try:
            health = self._registry.health(self._provider_id)
        except KeyError:
            state = ComponentState.NOT_CONFIGURED
            detail = "provider is not registered"
        else:
            state = {
                ProviderHealth.HEALTHY: ComponentState.ONLINE,
                ProviderHealth.DEGRADED: ComponentState.DEGRADED,
                ProviderHealth.UNAVAILABLE: ComponentState.OFFLINE,
                ProviderHealth.CIRCUIT_OPEN: ComponentState.DEGRADED,
            }[health]
            detail = f"health={health.value}"
        return ComponentStatus(
            component_id=self.component_id,
            label=f"Provider {self._provider_id.value}",
            category="provider",
            state=state,
            detail=detail,
        )
