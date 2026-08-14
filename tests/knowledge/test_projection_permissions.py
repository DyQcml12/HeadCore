from __future__ import annotations

from datetime import UTC, datetime

from app.knowledge import (
    InMemoryKnowledgeRepository,
    KnowledgeActor,
    KnowledgeLifecycleService,
    MemoryDecision,
    MemoryDecisionKind,
    MemoryScope,
    PortraitPatch,
)


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


async def test_scope_and_relationship_projection_matrix() -> None:
    repository = InMemoryKnowledgeRepository()
    ids = iter(f"id-{index}" for index in range(100))
    service = KnowledgeLifecycleService(repository, clock=lambda: NOW, id_factory=lambda: next(ids))
    owner = KnowledgeActor(profile_id="p1", persona_id="persona-a")
    admin = KnowledgeActor(profile_id="p1", persona_id="persona-a", verified=True, is_admin=True)

    cases = (
        (MemoryScope.SAFE_PREFERENCE, None, "safe"),
        (MemoryScope.PROFILE_PRIVATE, None, "private"),
        (MemoryScope.PERSONA_SPECIFIC, "persona-a", "persona"),
        (MemoryScope.ADMIN_PRIVATE, None, "admin"),
    )
    for scope, persona_id, value in cases:
        candidate = await service.submit(
            PortraitPatch(
                profile_id="p1", key=f"key.{value}", value=value, scope=scope,
                source_type="message", source_id=f"message-{value}", confidence=0.9,
                persona_id=persona_id,
            ),
            actor=admin if scope == MemoryScope.ADMIN_PRIVATE else owner,
        )
        await service.decide(
            candidate.id,
            MemoryDecision(
                kind=MemoryDecisionKind.APPROVE, reason="approved",
                decided_by_profile_id="admin", decided_at=NOW,
            ),
        )

    assert {item.value for item in await service.project(actor=owner)} == {"safe", "private", "persona"}
    assert {item.value for item in await service.project(actor=admin)} == {"safe", "private", "persona", "admin"}
    other_persona = KnowledgeActor(profile_id="p1", persona_id="persona-b")
    assert {item.value for item in await service.project(actor=other_persona)} == {"safe", "private"}
    blocked = KnowledgeActor(profile_id="p1", persona_id="persona-a", relationship_type="blocked")
    assert await service.project(actor=blocked) == ()


async def test_projection_does_not_expose_raw_provenance() -> None:
    repository = InMemoryKnowledgeRepository()
    service = KnowledgeLifecycleService(repository, clock=lambda: NOW)
    owner = KnowledgeActor(profile_id="p1")
    candidate = await service.submit(
        PortraitPatch(
            profile_id="p1", key="reply.style", value="short", scope=MemoryScope.SAFE_PREFERENCE,
            source_type="private_message", source_id="secret-message-id", confidence=0.8,
        ),
        actor=owner,
    )
    await service.decide(
        candidate.id,
        MemoryDecision(
            kind=MemoryDecisionKind.APPROVE, reason="approved",
            decided_by_profile_id="admin", decided_at=NOW,
        ),
    )

    projection = (await service.project(actor=owner))[0]
    assert not hasattr(projection, "source_id")
    assert not hasattr(projection, "source_type")
