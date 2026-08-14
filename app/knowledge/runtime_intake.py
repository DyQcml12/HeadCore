from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.database_control.contracts import ActorIdentity
from app.database_control.mysql_adapter import MySQLDatabaseControlAdapter
from app.knowledge.intake import MemoryCandidateIntakeService
from app.knowledge.models import KnowledgeActor, MemoryScope
from app.knowledge.mysql_repository import MySQLKnowledgeRepository
from app.knowledge.service import KnowledgeLifecycleService
from app.perception.contracts import PerceptionObservation
from app.perception.knowledge import observation_to_memory_candidate


@dataclass(frozen=True)
class RuntimeMemoryIntakeResult:
    status: str
    reason: str
    candidate_id: str = ""


class RuntimeMemoryCandidateCoordinator:
    def __init__(
        self,
        settings: Settings,
        knowledge_repository: MySQLKnowledgeRepository,
        actor_repository: MySQLDatabaseControlAdapter,
    ) -> None:
        self._settings = settings
        self._knowledge_repository = knowledge_repository
        self._actor_repository = actor_repository
        self._intake = MemoryCandidateIntakeService(
            KnowledgeLifecycleService(knowledge_repository)
        )

    async def submit_observation(
        self,
        observation: PerceptionObservation,
        *,
        platform: str,
        platform_user_id: str,
        platform_group_id: str | None,
        source_id: str,
        key: str,
    ) -> RuntimeMemoryIntakeResult:
        if not self._settings.knowledge_candidate_intake_enabled:
            return RuntimeMemoryIntakeResult("disabled", "feature_disabled")
        try:
            readiness = await self._knowledge_repository.get_persistence_status()
            if not readiness.write_ready:
                return RuntimeMemoryIntakeResult("unavailable", readiness.reason)
            database_actor = await self._actor_repository.resolve_actor(
                ActorIdentity(
                    platform=platform,  # type: ignore[arg-type]
                    platform_user_id=platform_user_id,
                    platform_group_id=platform_group_id or "",
                )
            )
            if database_actor is None:
                return RuntimeMemoryIntakeResult("rejected", "identity_unbound")
            is_admin = database_actor.relationship_type == "admin_partner"
            actor = KnowledgeActor(
                profile_id=database_actor.profile_id,
                account_id=database_actor.source_account.id,
                relationship_type=database_actor.relationship_type,
                verified=is_admin,
                is_admin=is_admin,
                can_write_long_term_memory=database_actor.permissions.mutate_admin,
            )
            candidate_input = observation_to_memory_candidate(
                observation,
                profile_id=database_actor.profile_id,
                source_id=source_id,
                key=key,
                scope=MemoryScope.PROFILE_PRIVATE,
            )
            result = await self._intake.submit(
                candidate_input,
                actor=actor,
                identity_bound=True,
            )
            return RuntimeMemoryIntakeResult(
                result.status,
                result.reason,
                result.candidate.id if result.candidate else "",
            )
        except Exception:
            return RuntimeMemoryIntakeResult("unavailable", "intake_failed")


def build_runtime_memory_candidate_coordinator(
    settings: Settings,
) -> RuntimeMemoryCandidateCoordinator | None:
    if not settings.knowledge_candidate_intake_enabled:
        return None
    if not settings.database_v2_enabled:
        return None
    if not all((settings.mysql_database, settings.mysql_user, settings.mysql_password)):
        return None
    knowledge_repository = MySQLKnowledgeRepository(settings)
    return RuntimeMemoryCandidateCoordinator(
        settings,
        knowledge_repository,
        MySQLDatabaseControlAdapter(settings),
    )
