from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from app.database_control.actor import require_mutate_admin, require_read_admin
from app.database_control.contracts import ActorIdentity, DatabaseActor
from app.database_control.errors import DatabaseNotReadyError, ResourceNotFoundError
from app.knowledge.models import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    KnowledgeActor,
    MemoryCandidate,
    MemoryDecision,
    MemoryDecisionKind,
    MemoryRecord,
    MemoryState,
)
from app.knowledge.mysql_repository import MySQLKnowledgeRepository
from app.knowledge.readiness import KnowledgePersistenceStatus
from app.knowledge.service import KnowledgeLifecycleService


class KnowledgeActorResolver(Protocol):
    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None: ...


class KnowledgeControlService:
    def __init__(
        self,
        repository: MySQLKnowledgeRepository,
        actor_resolver: KnowledgeActorResolver,
    ) -> None:
        self._repository = repository
        self._actor_resolver = actor_resolver
        self._lifecycle = KnowledgeLifecycleService(repository)

    async def resolve_actor(self, identity: ActorIdentity, *, write: bool = False) -> DatabaseActor:
        actor = await self._actor_resolver.resolve_actor(identity)
        if actor is None:
            from app.database_control.errors import UnauthenticatedError
            raise UnauthenticatedError("database actor identity could not be resolved")
        require_mutate_admin(actor) if write else require_read_admin(actor)
        return actor

    async def status(self, actor: DatabaseActor) -> KnowledgePersistenceStatus:
        require_read_admin(actor)
        return await self._repository.get_persistence_status()

    async def list_candidates(
        self,
        actor: DatabaseActor,
        *,
        profile_id: str | None,
        state: MemoryState | None,
        limit: int,
    ) -> tuple[MemoryCandidate, ...]:
        require_read_admin(actor)
        return await self._repository.list_candidates(
            profile_id=profile_id, state=state, limit=limit
        )

    async def decide(
        self,
        actor: DatabaseActor,
        candidate_id: str,
        *,
        kind: MemoryDecisionKind,
        reason: str,
        supersede_conflicts: bool,
    ) -> MemoryRecord | None:
        require_mutate_admin(actor)
        await self._require_ready()
        try:
            return await self._lifecycle.decide(
                candidate_id,
                MemoryDecision(
                    kind=kind,
                    reason=reason,
                    decided_by_profile_id=actor.profile_id,
                    decided_at=datetime.now(UTC),
                    supersede_conflicts=supersede_conflicts,
                ),
            )
        except EntityNotFoundError as exc:
            raise ResourceNotFoundError("memory candidate was not found") from exc

    async def revoke(
        self, actor: DatabaseActor, record_id: str, *, reason: str
    ) -> MemoryRecord:
        require_mutate_admin(actor)
        await self._require_ready()
        try:
            return await self._lifecycle.revoke(
                record_id,
                actor=KnowledgeActor(
                    profile_id=actor.profile_id,
                    relationship_type=actor.relationship_type,
                    verified=True,
                    is_admin=True,
                    can_write_long_term_memory=True,
                ),
                reason=reason,
            )
        except EntityNotFoundError as exc:
            raise ResourceNotFoundError("memory record was not found") from exc

    async def _require_ready(self) -> None:
        status = await self._repository.get_persistence_status()
        if not status.write_ready:
            raise DatabaseNotReadyError(status.reason)
