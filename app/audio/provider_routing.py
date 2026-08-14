from __future__ import annotations

import asyncio
from pathlib import Path

from app.providers import (
    AsrRequest,
    ProviderCapability,
    ProviderId,
    ProviderRegistry,
    ProviderRouter,
    RoutingFailed,
    RoutingPolicy,
)
from app.providers.funasr import FunAsrProvider


class RoutedFileAsrEngine:
    def __init__(
        self,
        engine: object,
        *,
        provider_id: str,
        timeout_seconds: float,
        circuit_failure_threshold: int,
        circuit_recovery_seconds: float,
    ) -> None:
        self.provider = str(getattr(engine, "provider", "funasr"))
        self.model = str(getattr(engine, "model", provider_id))
        self._provider_id = ProviderId(provider_id)
        registry = ProviderRegistry()
        registry.register(FunAsrProvider(self._provider_id, engine))
        self._router = ProviderRouter(registry)
        self._policy = RoutingPolicy(
            providers=(self._provider_id,),
            timeout_seconds=timeout_seconds,
            retries_per_provider=0,
            circuit_failure_threshold=circuit_failure_threshold,
            circuit_recovery_seconds=circuit_recovery_seconds,
        )

    def transcribe_file(self, audio_path: Path):
        try:
            decision = asyncio.run(
                self._router.route(
                    ProviderCapability.ASR,
                    self._policy,
                    lambda provider: provider.transcribe(AsrRequest(audio_path)),
                )
            )
        except RoutingFailed as exc:
            raise exc.last_error or exc from exc
        return decision.value
