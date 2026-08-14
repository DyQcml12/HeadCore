from __future__ import annotations

from dataclasses import replace

from app.core.config import load_settings
from app.knowledge import InMemoryKnowledgeRepository
from app.knowledge.readiness import (
    KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES,
    assess_knowledge_persistence,
)
from app.knowledge.runtime_intake import (
    RuntimeMemoryCandidateCoordinator,
    build_runtime_memory_candidate_coordinator,
)
from app.perception.contracts import (
    MemoryDecision,
    MemoryEligibility,
    PerceptionModality,
    PerceptionObservation,
    PerceptionQuality,
)
from tests.database_control.fakes import actor


class RuntimeKnowledgeRepository(InMemoryKnowledgeRepository):
    def __init__(self, *, ready: bool = True) -> None:
        super().__init__()
        self.ready = ready

    async def get_persistence_status(self):  # type: ignore[no-untyped-def]
        return assess_knowledge_persistence(
            set(KNOWLEDGE_LIFECYCLE_REQUIRED_TABLES) if self.ready else set(),
            migration_applied=self.ready,
        )


class ActorRepository:
    def __init__(self, resolved) -> None:  # type: ignore[no-untyped-def]
        self.resolved = resolved

    async def resolve_actor(self, identity):  # type: ignore[no-untyped-def]
        return self.resolved


def settings(*, enabled: bool = True):  # type: ignore[no-untyped-def]
    return replace(
        load_settings(),
        database_v2_enabled=True,
        knowledge_candidate_intake_enabled=enabled,
        mysql_database="test_knowledge",
        mysql_user="test",
        mysql_password="test",
    )


def observation() -> PerceptionObservation:
    return PerceptionObservation(
        modality=PerceptionModality.AUDIO,
        source="qq",
        text="prefer concise replies",
        confidence=0.9,
        quality=PerceptionQuality.GOOD,
        memory_eligibility=MemoryEligibility(decision=MemoryDecision.ALLOW),
    )


async def submit(coordinator):  # type: ignore[no-untyped-def]
    return await coordinator.submit_observation(
        observation(),
        platform="qq",
        platform_user_id="10001",
        platform_group_id=None,
        source_id="qq:message-1:audio",
        key="perception.audio.summary",
    )


def test_factory_is_off_by_default() -> None:
    assert build_runtime_memory_candidate_coordinator(load_settings()) is None


async def test_ready_admin_observation_creates_one_idempotent_candidate() -> None:
    repository = RuntimeKnowledgeRepository()
    coordinator = RuntimeMemoryCandidateCoordinator(
        settings(), repository, ActorRepository(actor())  # type: ignore[arg-type]
    )

    first = await submit(coordinator)
    second = await submit(coordinator)

    assert first.status == "candidate"
    assert first.candidate_id == second.candidate_id
    assert [event.action for event in await repository.list_audit_events()] == ["submitted"]


async def test_schema_not_ready_does_not_resolve_actor_or_write() -> None:
    repository = RuntimeKnowledgeRepository(ready=False)

    class UnexpectedActorRepository:
        async def resolve_actor(self, identity):  # type: ignore[no-untyped-def]
            raise AssertionError("actor lookup should not run")

    coordinator = RuntimeMemoryCandidateCoordinator(
        settings(), repository, UnexpectedActorRepository()  # type: ignore[arg-type]
    )
    result = await submit(coordinator)

    assert result.status == "unavailable"
    assert result.reason == "lifecycle_migration_missing"
    assert await repository.list_audit_events() == ()


async def test_unbound_and_normal_friend_are_rejected_without_candidate() -> None:
    for resolved, expected in ((None, "identity_unbound"), (actor("normal_friend"), "memory_write_forbidden")):
        repository = RuntimeKnowledgeRepository()
        coordinator = RuntimeMemoryCandidateCoordinator(
            settings(), repository, ActorRepository(resolved)  # type: ignore[arg-type]
        )
        result = await submit(coordinator)
        assert result.status == "rejected"
        assert result.reason == expected
        assert await repository.list_audit_events() == ()
