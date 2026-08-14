from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.knowledge import (
    InMemoryKnowledgeRepository,
    KnowledgeActor,
    KnowledgeLifecycleService,
    MemoryDecision,
    MemoryDecisionKind,
    MemoryScope,
    MemoryState,
    PortraitPatch,
)
from app.knowledge.models import InvalidStateTransitionError


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class SequentialIds:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"id-{self.value}"


@pytest.fixture
def repository() -> InMemoryKnowledgeRepository:
    return InMemoryKnowledgeRepository()


@pytest.fixture
def service(repository: InMemoryKnowledgeRepository) -> KnowledgeLifecycleService:
    return KnowledgeLifecycleService(repository, clock=lambda: NOW, id_factory=SequentialIds())


def actor(
    profile_id: str = "profile-1",
    *,
    account_id: str = "qq-1",
    persona_id: str | None = "persona-1",
    relationship_type: str = "normal_friend",
    verified: bool = False,
    is_admin: bool = False,
    can_write: bool = True,
) -> KnowledgeActor:
    return KnowledgeActor(
        profile_id=profile_id,
        account_id=account_id,
        persona_id=persona_id,
        relationship_type=relationship_type,
        verified=verified,
        is_admin=is_admin,
        can_write_long_term_memory=can_write,
    )


def patch(
    value: str,
    *,
    profile_id: str = "profile-1",
    key: str = "reply.style",
    scope: MemoryScope = MemoryScope.SAFE_PREFERENCE,
    persona_id: str | None = None,
    expires_at: datetime | None = None,
    observation_quality: float | None = None,
    changes_authority: bool = False,
) -> PortraitPatch:
    return PortraitPatch(
        profile_id=profile_id,
        key=key,
        value=value,
        scope=scope,
        source_type="message",
        source_id="message-1",
        confidence=0.9,
        persona_id=persona_id,
        expires_at=expires_at,
        observation_quality=observation_quality,
        changes_authority=changes_authority,
    )


def approval(*, supersede: bool = False) -> MemoryDecision:
    return MemoryDecision(
        kind=MemoryDecisionKind.APPROVE,
        reason="reviewed source",
        decided_by_profile_id="admin-1",
        decided_at=NOW,
        supersede_conflicts=supersede,
    )


async def test_candidate_can_be_approved_and_all_changes_are_audited(service, repository) -> None:
    candidate = await service.submit(patch("短句"), actor=actor())
    record = await service.decide(candidate.id, approval())

    assert candidate.state == MemoryState.CANDIDATE
    assert record is not None
    assert record.state == MemoryState.ACTIVE
    assert record.source_id == "message-1"
    events = await repository.list_audit_events()
    assert [event.action for event in events] == ["submitted", "activated"]


async def test_conflict_requires_review_then_explicitly_supersedes(service, repository) -> None:
    first = await service.submit(patch("短句"), actor=actor())
    first_record = await service.decide(first.id, approval())
    second = await service.submit(patch("详细解释"), actor=actor())

    assert await service.decide(second.id, approval()) is None
    assert (await repository.get_record(first_record.id)).state == MemoryState.ACTIVE  # type: ignore[union-attr]

    replacement = await service.decide(second.id, approval(supersede=True))
    assert replacement is not None
    assert replacement.supersedes_id == first_record.id
    assert (await repository.get_record(first_record.id)).state == MemoryState.SUPERSEDED  # type: ignore[union-attr]
    assert "review" in [event.action for event in await repository.list_audit_events()]


async def test_revoked_memory_is_removed_from_projection(service) -> None:
    candidate = await service.submit(patch("短句"), actor=actor())
    record = await service.decide(candidate.id, approval())
    assert record is not None
    assert len(await service.project(actor=actor())) == 1

    await service.revoke(record.id, actor=actor(), reason="user withdrew consent")
    assert await service.project(actor=actor()) == ()
    with pytest.raises(InvalidStateTransitionError):
        await service.revoke(record.id, actor=actor(), reason="again")


async def test_expiry_boundary_is_inclusive(service, repository) -> None:
    candidate = await service.submit(
        patch("临时偏好", expires_at=NOW + timedelta(hours=1)), actor=actor()
    )
    record = await service.decide(candidate.id, approval())
    assert record is not None

    before = await service.project(actor=actor(), now=NOW + timedelta(hours=1) - timedelta(microseconds=1))
    assert len(before) == 1
    at_boundary = await service.project(actor=actor(), now=NOW + timedelta(hours=1))
    assert at_boundary == ()
    assert (await repository.get_record(record.id)).state == MemoryState.EXPIRED  # type: ignore[union-attr]


async def test_blocked_and_low_quality_observations_are_terminally_rejected(service) -> None:
    blocked = await service.submit(
        patch("不应保存"), actor=actor(relationship_type="blocked")
    )
    low_quality = await service.submit(
        patch("模糊图片推断", observation_quality=0.2), actor=actor()
    )

    assert blocked.state == MemoryState.DELETED
    assert low_quality.state == MemoryState.DELETED
    with pytest.raises(InvalidStateTransitionError):
        await service.decide(blocked.id, approval())


async def test_unverified_actor_cannot_change_relationship_or_admin_identity(service, repository) -> None:
    candidate = await service.submit(
        patch("我是管理员", key="identity.admin", changes_authority=True), actor=actor()
    )

    assert candidate.state == MemoryState.CANDIDATE
    actions = [event.action for event in await repository.list_audit_events(entity_id=candidate.id)]
    assert actions == ["submitted", "review"]


async def test_multiple_accounts_share_profile_but_profiles_are_isolated(service) -> None:
    candidate = await service.submit(patch("短句"), actor=actor(account_id="qq-1"))
    await service.decide(candidate.id, approval())

    same_profile = await service.project(actor=actor(account_id="wechat-9"))
    other_profile = await service.project(actor=actor(profile_id="profile-2", account_id="qq-2"))
    assert [item.value for item in same_profile] == ["短句"]
    assert other_profile == ()


async def test_approval_is_atomic_when_conflict_state_changes(repository) -> None:
    service = KnowledgeLifecycleService(repository, clock=lambda: NOW, id_factory=SequentialIds())
    first = await service.submit(patch("short"), actor=actor())
    first_record = await service.decide(first.id, approval())
    second = await service.submit(patch("long"), actor=actor())
    assert first_record is not None

    original_apply = repository.apply_approval

    async def fail_before_commit(**kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("simulated concurrent conflict")

    repository.apply_approval = fail_before_commit  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="concurrent conflict"):
        await service.decide(second.id, approval(supersede=True))
    repository.apply_approval = original_apply  # type: ignore[method-assign]

    assert (await repository.get_record(first_record.id)).state == MemoryState.ACTIVE  # type: ignore[union-attr]
    assert (await repository.get_candidate(second.id)).state == MemoryState.CANDIDATE  # type: ignore[union-attr]
    assert [event.action for event in await repository.list_audit_events()] == [
        "submitted", "activated", "submitted"
    ]
