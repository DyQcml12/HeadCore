from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.database_control.service import DatabaseControlRepository
from app.operations.contracts import ComponentState, ComponentStatus, DependencyStatus
from app.operations.probes import StaticStatusProvider
from app.operations.providers import StatusProvider
from app.audio.funasr_engine import MODEL_PRESETS
from app.audio.model_paths import resolve_modelscope_model
from app.providers import ProviderHealth
from app.providers.runtime import ProviderRuntimeMonitor, provider_runtime_monitor
from app.knowledge.mysql_repository import MySQLKnowledgeRepository


class DatabaseControlStatusProvider:
    component_id = "database_v2"

    def __init__(self, repository: DatabaseControlRepository) -> None:
        self._repository = repository

    async def get_status(self) -> ComponentStatus:
        status = await self._repository.get_status()
        if not status.database_v2_enabled:
            state = ComponentState.NOT_CONFIGURED
            detail = "Database V2 is disabled"
        elif status.ready:
            state = ComponentState.ONLINE
            detail = "schema and administrator bootstrap are ready"
        else:
            state = ComponentState.DEGRADED
            missing_count = sum(1 for present in status.required_tables.values() if not present)
            detail = f"readiness failed; missing tables: {missing_count}"
        return ComponentStatus(
            component_id=self.component_id,
            label="Database V2",
            category="database",
            state=state,
            detail=detail,
        )


class ProviderRuntimeStatusProvider:
    component_id = "provider_runtime"

    def __init__(self, monitor: ProviderRuntimeMonitor = provider_runtime_monitor) -> None:
        self._monitor = monitor

    async def get_status(self) -> ComponentStatus:
        statuses = self._monitor.snapshot()
        unhealthy = [item for item in statuses if item.health is not ProviderHealth.HEALTHY]
        open_count = sum(1 for item in statuses if item.circuit_open)
        error_codes = sorted({item.last_error_code.value for item in unhealthy if item.last_error_code})
        detail = f"tracked={len(statuses)}; degraded={len(unhealthy)}; open_circuits={open_count}"
        if error_codes:
            detail += "; error_codes=" + ",".join(error_codes)
        return ComponentStatus(
            component_id=self.component_id,
            label="Provider runtime",
            category="provider",
            state=ComponentState.DEGRADED if unhealthy else ComponentState.ONLINE,
            detail=detail,
        )


class KnowledgeLifecycleStatusProvider:
    component_id = "knowledge_lifecycle"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_status(self) -> ComponentStatus:
        if not self._settings.database_v2_enabled:
            return ComponentStatus(
                component_id=self.component_id, label="Knowledge lifecycle",
                category="memory", state=ComponentState.NOT_CONFIGURED,
                detail="Database V2 is disabled",
            )
        if not all((self._settings.mysql_database, self._settings.mysql_user, self._settings.mysql_password)):
            return ComponentStatus(
                component_id=self.component_id, label="Knowledge lifecycle",
                category="memory", state=ComponentState.NOT_CONFIGURED,
                detail="MySQL settings are incomplete",
            )
        try:
            status = await MySQLKnowledgeRepository(self._settings).get_persistence_status()
        except Exception:
            return ComponentStatus(
                component_id=self.component_id, label="Knowledge lifecycle",
                category="memory", state=ComponentState.DEGRADED,
                detail="readiness query failed",
            )
        return ComponentStatus(
            component_id=self.component_id,
            label="Knowledge lifecycle",
            category="memory",
            state=ComponentState.ONLINE if status.durable else ComponentState.DEGRADED,
            detail=(
                "projection repository is ready"
                if status.durable
                else status.reason
            ),
        )


def build_project_status_providers(
    *,
    settings: Settings,
    database_repository: DatabaseControlRepository,
    workspace_root: Path,
) -> tuple[StatusProvider, ...]:
    model_configured = bool(settings.model_provider and settings.model_name)
    if settings.model_provider == "deepseek":
        model_configured = model_configured and bool(settings.deepseek_api_key)

    asr_configured, asr_ready, asr_detail = asr_model_readiness(settings.asr_file_presets)

    return (
        StaticStatusProvider("core_api", "Core API", "service", configured=True, ready=True),
        DatabaseControlStatusProvider(database_repository),
        KnowledgeLifecycleStatusProvider(settings),
        StaticStatusProvider(
            "text_model",
            "Text model",
            "provider",
            configured=model_configured,
            ready=model_configured,
        ),
        StaticStatusProvider(
            "asr_model",
            "ASR model",
            "provider",
            configured=asr_configured,
            ready=asr_ready,
            detail=asr_detail,
        ),
        ProviderRuntimeStatusProvider(),
    )


def asr_model_readiness(presets: str) -> tuple[bool, bool, str]:
    names = tuple(dict.fromkeys(item.strip() for item in presets.split(",") if item.strip()))
    if not names:
        return False, False, "no ASR preset configured"
    unknown = [name for name in names if name not in MODEL_PRESETS]
    if unknown:
        return False, False, f"unknown presets: {', '.join(unknown)}"
    available: list[str] = []
    for name in names:
        resolved = resolve_modelscope_model(str(MODEL_PRESETS[name]["model"]))
        if Path(resolved).is_dir():
            available.append(name)
    if available:
        return True, True, f"local presets ready: {', '.join(available)}"
    return True, False, "configured ASR models are not available locally"
