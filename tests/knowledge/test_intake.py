from __future__ import annotations

from datetime import UTC, datetime

from app.knowledge import (
    InMemoryKnowledgeRepository,
    KnowledgeActor,
    KnowledgeLifecycleService,
    MemoryCandidateInput,
    MemoryCandidateIntakeService,
    MemoryScope,
)
from app.perception.contracts import (
    MemoryDecision,
    MemoryEligibility,
    PerceptionModality,
    PerceptionObservation,
    PerceptionQuality,
    ProviderTrace,
)
from app.perception.knowledge import observation_to_memory_candidate


NOW = datetime(2026, 7, 15, 3, 0, tzinfo=UTC)


def actor(**overrides) -> KnowledgeActor:  # type: ignore[no-untyped-def]
    values = {
        "profile_id": "profile-1",
        "relationship_type": "admin_partner",
        "verified": True,
        "is_admin": True,
        "can_write_long_term_memory": True,
    }
    values.update(overrides)
    return KnowledgeActor(**values)


def value(**overrides) -> MemoryCandidateInput:  # type: ignore[no-untyped-def]
    values = {
        "profile_id": "profile-1",
        "key": "reply.style",
        "value": "prefer concise replies",
        "scope": MemoryScope.SAFE_PREFERENCE,
        "source_type": "perception:audio",
        "source_id": "message-1:audio-1",
        "confidence": 0.9,
        "eligibility": "allow",
        "observation_quality": 1.0,
    }
    values.update(overrides)
    return MemoryCandidateInput(**values)


def service():  # type: ignore[no-untyped-def]
    repository = InMemoryKnowledgeRepository()
    lifecycle = KnowledgeLifecycleService(repository, clock=lambda: NOW)
    return MemoryCandidateIntakeService(lifecycle), repository


async def test_allow_creates_candidate_but_does_not_activate_memory() -> None:
    intake, repository = service()
    result = await intake.submit(value(), actor=actor(), identity_bound=True)

    assert result.status == "candidate"
    assert result.candidate is not None
    assert result.candidate.state == "candidate"
    assert await repository.list_records(profile_id="profile-1") == ()


async def test_review_creates_reviewable_candidate_only() -> None:
    intake, repository = service()
    result = await intake.submit(
        value(eligibility="review", eligibility_reasons=("requires_review",), observation_quality=0.7),
        actor=actor(),
        identity_bound=True,
    )

    assert result.status == "review"
    assert result.reason == "requires_review"
    assert result.candidate is not None
    assert await repository.list_records(profile_id="profile-1") == ()


async def test_rejected_inputs_do_not_touch_repository() -> None:
    cases = (
        (value(eligibility="deny", eligibility_reasons=("low_confidence",)), actor(), True, "low_confidence"),
        (value(), actor(relationship_type="blocked"), True, "profile_blocked"),
        (value(), actor(), False, "identity_unbound"),
        (value(profile_id="profile-2"), actor(is_admin=False, verified=False), True, "profile_mismatch"),
    )
    for candidate_input, candidate_actor, bound, reason in cases:
        intake, repository = service()
        result = await intake.submit(candidate_input, actor=candidate_actor, identity_bound=bound)
        assert result.status == "rejected"
        assert result.reason == reason
        assert await repository.list_audit_events() == ()


async def test_duplicate_source_returns_existing_candidate_without_duplicate_audit() -> None:
    intake, repository = service()
    first = await intake.submit(value(), actor=actor(), identity_bound=True)
    second = await intake.submit(value(value="changed retry body"), actor=actor(), identity_bound=True)

    assert first.candidate == second.candidate
    assert second.candidate is not None
    assert second.candidate.value == "prefer concise replies"
    assert [event.action for event in await repository.list_audit_events()] == ["submitted"]


def test_s3_bridge_maps_only_safe_observation_fields() -> None:
    observation = PerceptionObservation(
        modality=PerceptionModality.AUDIO,
        source="qq",
        text="prefer concise replies",
        confidence=0.91,
        quality=PerceptionQuality.GOOD,
        traces=(
            ProviderTrace(
                provider="funasr", success=True,
                error_message="private URL http://127.0.0.1/token=secret",
            ),
        ),
        memory_eligibility=MemoryEligibility(decision=MemoryDecision.ALLOW),
        metadata={"temporary_url": "http://private/token"},
    )

    mapped = observation_to_memory_candidate(
        observation,
        profile_id="profile-1",
        source_id="message-1:audio-1",
        key="reply.style",
    )

    assert mapped.value == "prefer concise replies"
    assert mapped.source_type == "perception:audio"
    assert mapped.eligibility == "allow"
    assert not hasattr(mapped, "traces")
    assert not hasattr(mapped, "metadata")
