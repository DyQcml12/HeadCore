from __future__ import annotations

import datetime as dt
import asyncio

import pytest

from app.head.contracts import (
    CausalHypothesis,
    WorldAssertionStatus,
    WorldEntity,
    WorldEvent,
    WorldRelation,
)
from app.head.world_model import (
    DEFAULT_BELIEF_HALF_LIFE,
    belief_strength,
    build_head_world_model,
    project_head_world_model,
)
from app.head.world_model_store import load_head_world_model, save_head_world_model
from app.head.events import load_head_event_context
from app.storage.chat_repository import JsonlChatRepository
from app.head.contracts import HeadEventContext
from app.head.state import build_head_state
from app.mind.conversation_state import build_conversation_state
from app.mind.self_state import build_self_state
from app.mind.social_state import build_social_state
from app.persona.relationship_context import DEFAULT_RELATIONSHIP_CONTEXT


NOW = dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC)
ENTITIES = (
    WorldEntity("user", "person", "用户"),
    WorldEntity("project", "software", "HutaoChatCore"),
    WorldEntity("server-a", "service", "Core 服务"),
)


def relation(relation_id: str, object_id: str, *, until: str | None = None) -> WorldRelation:
    return WorldRelation(
        relation_id=relation_id,
        subject_id="project",
        predicate="uses_service",
        object_id=object_id,
        source_id="runtime",
        valid_from="2026-07-22T10:00:00+00:00",
        valid_until=until,
        confidence=0.9,
    )


def event(event_id: str, occurred_at: str, summary: str) -> WorldEvent:
    return WorldEvent(
        event_id=event_id,
        event_type="deployment",
        actor_ids=("project", "server-a"),
        occurred_at=occurred_at,
        source_id="runtime",
        summary=summary,
        confidence=0.9,
    )


def test_active_relation_and_events_are_projected_in_time_order() -> None:
    model = build_head_world_model(
        entities=ENTITIES,
        relations=(relation("r1", "server-a"),),
        events=(
            event("later", "2026-07-22T11:00:00+00:00", "完成服务恢复"),
            event("earlier", "2026-07-22T10:30:00+00:00", "服务出现中断"),
        ),
        now=NOW,
    )
    projection = project_head_world_model(model, now=NOW)

    assert model.events[0].event_id == "earlier"
    assert "HutaoChatCore|uses_service|Core 服务" in projection[0]
    assert "完成服务恢复" in projection[1]


def test_expired_relation_is_retained_but_not_projected() -> None:
    model = build_head_world_model(
        entities=ENTITIES,
        relations=(relation("r1", "server-a", until="2026-07-22T11:00:00+00:00"),),
        now=NOW,
    )
    assert model.relations[0].status == WorldAssertionStatus.STALE
    assert project_head_world_model(model, now=NOW) == ()


def test_old_event_is_auditable_but_not_current_context() -> None:
    model = build_head_world_model(
        entities=ENTITIES,
        events=(event("old", "2026-05-01T10:00:00+00:00", "旧服务事件"),),
        now=NOW,
    )

    assert model.events[0].event_id == "old"
    assert project_head_world_model(model, now=NOW) == ()
    assert model.uncertainties == ("world_event_stale:deployment",)


def test_conflicting_relation_values_become_uncertainty() -> None:
    entities = ENTITIES + (WorldEntity("server-b", "service", "备用服务"),)
    model = build_head_world_model(
        entities=entities,
        relations=(relation("r1", "server-a"), relation("r2", "server-b")),
        now=NOW,
    )
    assert {item.status for item in model.relations} == {WorldAssertionStatus.CONFLICTED}
    assert model.uncertainties == ("关系冲突:project.uses_service",)
    assert project_head_world_model(model) == ()


def test_unconfirmed_causality_is_explicitly_projected_as_hypothesis() -> None:
    events = (
        event("cause", "2026-07-22T10:00:00+00:00", "配置发生变化"),
        event("effect", "2026-07-22T10:05:00+00:00", "服务出现中断"),
    )
    model = build_head_world_model(
        entities=ENTITIES,
        events=events,
        causal_hypotheses=(
            CausalHypothesis(
                "h1", "cause", "effect", "配置变化可能导致服务中断", 0.6, ("cause",), False
            ),
        ),
        now=NOW,
    )
    assert "因果待验证:h1" in model.uncertainties
    assert any("因果假设(不得当作事实)" in value for value in project_head_world_model(model))


def test_confirmed_causality_requires_strong_evidence() -> None:
    events = (
        event("cause", "2026-07-22T10:00:00+00:00", "配置发生变化"),
        event("effect", "2026-07-22T10:05:00+00:00", "服务出现中断"),
    )
    with pytest.raises(ValueError, match="requires evidence"):
        build_head_world_model(
            entities=ENTITIES,
            events=events,
            causal_hypotheses=(CausalHypothesis("h1", "cause", "effect", "存在因果", 0.7, (), True),),
            now=NOW,
        )


def test_unknown_entity_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown entity"):
        build_head_world_model(
            entities=ENTITIES,
            relations=(relation("r1", "missing"),),
            now=NOW,
        )


def test_world_model_flows_into_head_state_known_and_uncertain_context() -> None:
    model = build_head_world_model(
        entities=ENTITIES,
        relations=(relation("r1", "server-a"),),
        events=(
            event("cause", "2026-07-22T10:00:00+00:00", "配置发生变化"),
            event("effect", "2026-07-22T10:05:00+00:00", "服务出现中断"),
        ),
        causal_hypotheses=(
            CausalHypothesis("h1", "cause", "effect", "配置变化可能导致中断", 0.6, ("cause",)),
        ),
        now=NOW,
    )
    conversation = build_conversation_state(user_input="继续处理项目", recent_messages=[])
    state = build_head_state(
        subject_id="user-1",
        user_input="继续处理项目",
        relationship_role="normal_friend",
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=build_social_state(
            relationship=DEFAULT_RELATIONSHIP_CONTEXT,
            conversation=conversation,
            recent_messages=[],
            user_input="继续处理项目",
        ),
        recent_messages=[],
        event_context=HeadEventContext(world_model=model),
    )

    assert state.world_model is model
    assert any("世界关系=" in value for value in state.known_context)
    assert "因果待验证:h1" in state.uncertainties


def test_world_model_persists_and_restores_through_head_event_context(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    model = build_head_world_model(
        entities=ENTITIES,
        relations=(relation("r1", "server-a"),),
        now=NOW,
    )
    asyncio.run(
        save_head_world_model(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message_id=None,
            model=model,
            allow_write=True,
        )
    )

    restored = asyncio.run(load_head_world_model(repository, user_id="user-1"))
    context = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    other_user = asyncio.run(load_head_world_model(repository, user_id="user-2"))

    assert restored.entities == model.entities
    assert context.world_model.entities == model.entities
    assert other_user.entities == ()


def test_belief_strength_decays_exponentially_and_reproducibly() -> None:
    since = dt.datetime(2026, 6, 22, 12, tzinfo=dt.UTC)
    now = dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC)

    assert belief_strength(0.9, since_at=since, now=now) == pytest.approx(0.45)
    assert belief_strength(0.9, since_at=now, now=now) == 0.9
    assert belief_strength(0.9, since_at=now, now=now - dt.timedelta(days=1)) == 0.9
    assert belief_strength(0.9, since_at=since, now=now) == belief_strength(
        0.9, since_at=since, now=now
    )


def test_stale_relation_enters_uncertainty_and_leaves_projection() -> None:
    old_relation = WorldRelation(
        relation_id="old-r",
        subject_id="project",
        predicate="uses_service",
        object_id="server-a",
        source_id="runtime",
        valid_from="2026-02-20T10:00:00+00:00",
        valid_until=None,
        confidence=0.9,
    )
    model = build_head_world_model(
        entities=ENTITIES,
        relations=(old_relation, relation("fresh-r", "server-a")),
        now=NOW,
    )

    assert "world_relation_stale:old-r" in model.uncertainties
    projection = project_head_world_model(model, now=NOW)
    assert all("旧" not in value for value in projection)
    assert any("uses_service" in value for value in projection)
    assert len(projection) == 1


def test_projection_orders_fresh_relation_before_aging_relation() -> None:
    aging_relation = WorldRelation(
        relation_id="aging-r",
        subject_id="project",
        predicate="uses_service",
        object_id="server-a",
        source_id="runtime",
        valid_from="2026-07-01T10:00:00+00:00",
        valid_until=None,
        confidence=0.9,
    )
    fresh_relation = WorldRelation(
        relation_id="fresh-r",
        subject_id="project",
        predicate="uses_service",
        object_id="server-a",
        source_id="runtime",
        valid_from="2026-07-22T11:00:00+00:00",
        valid_until=None,
        confidence=0.6,
    )
    model = build_head_world_model(
        entities=ENTITIES,
        relations=(aging_relation, fresh_relation),
        now=NOW,
    )

    projection = project_head_world_model(model, now=NOW)

    assert "confidence=0.60" in projection[0]
    assert "confidence=0.90" in projection[1]
    assert projection == project_head_world_model(model, now=NOW)


def test_world_model_write_policy_can_disable_persistence(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    model = build_head_world_model(entities=ENTITIES, now=NOW)
    asyncio.run(
        save_head_world_model(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message_id=None,
            model=model,
            allow_write=False,
        )
    )
    assert asyncio.run(load_head_world_model(repository, user_id="user-1")).entities == ()
