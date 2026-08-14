from __future__ import annotations

import asyncio
import datetime as dt
import json
from dataclasses import replace

from app.head import (
    CommunicationAct,
    FeedbackOutcome,
    HeadEventRecord,
    HeadAction,
    HeadEventContext,
    build_head_state,
    build_adaptive_policy,
    load_head_event_context,
    record_head_events,
    record_head_response_event,
    render_head_projection,
    selected_decision,
)
from app.mind.conversation_state import build_conversation_state
from app.mind.self_state import build_self_state
from app.mind.social_state import build_social_state
from app.persona.relationship_context import DEFAULT_RELATIONSHIP_CONTEXT
from app.storage.chat_repository import JsonlChatRepository


def build_state(user_input: str):
    conversation = build_conversation_state(user_input=user_input, recent_messages=[])
    self_state = build_self_state(conversation)
    social_state = build_social_state(
        relationship=DEFAULT_RELATIONSHIP_CONTEXT,
        conversation=conversation,
        recent_messages=[],
        user_input=user_input,
    )
    return build_head_state(
        subject_id="user-1",
        user_input=user_input,
        relationship_role=DEFAULT_RELATIONSHIP_CONTEXT.role,
        conversation=conversation,
        self_state=self_state,
        social_state=social_state,
        recent_messages=[],
    )


def test_head_state_continues_a_project_task() -> None:
    state = build_state("开始设计开发这个项目")
    assert state.current_topic == "technical_or_project"
    assert state.active_task != "none"
    assert state.decision.action == HeadAction.CONTINUE_TASK


def test_head_state_clarifies_an_ambiguous_request() -> None:
    state = build_state("这个怎么做？")
    assert state.uncertainties == ("指代对象不明确",)
    assert state.decision.action == HeadAction.CLARIFY


def test_head_state_clarifies_when_world_tool_requires_missing_input() -> None:
    user_input = "weather"
    conversation = build_conversation_state(user_input=user_input, recent_messages=[])
    state = build_head_state(
        subject_id="user-1",
        user_input=user_input,
        relationship_role=DEFAULT_RELATIONSHIP_CONTEXT.role,
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=build_social_state(
            relationship=DEFAULT_RELATIONSHIP_CONTEXT,
            conversation=conversation,
            recent_messages=[],
            user_input=user_input,
        ),
        recent_messages=[],
        additional_uncertainties=("world_input_required:weather_current",),
    )

    assert state.decision.action == HeadAction.CLARIFY
    assert state.decision.reason == "world_requires_input"


def test_head_state_marks_unavailable_world_evidence_without_fabrication() -> None:
    user_input = "weather"
    conversation = build_conversation_state(user_input=user_input, recent_messages=[])
    state = build_head_state(
        subject_id="user-1",
        user_input=user_input,
        relationship_role=DEFAULT_RELATIONSHIP_CONTEXT.role,
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=build_social_state(
            relationship=DEFAULT_RELATIONSHIP_CONTEXT,
            conversation=conversation,
            recent_messages=[],
            user_input=user_input,
        ),
        recent_messages=[],
        additional_uncertainties=("world_evidence_unavailable:weather_current",),
    )

    assert state.decision.action == HeadAction.ANSWER
    assert state.decision.reason == "world_evidence_unavailable"
    assert state.plan.rationale == "single_action_world_evidence"


def test_head_projection_keeps_unknowns_explicit() -> None:
    projection = render_head_projection(build_state("这个怎么做？"))
    assert "HeadCore 本轮认知快照" in projection
    assert "不确定=指代对象不明确" in projection
    assert "本轮行动=clarify" in projection
    assert "不要自行补全" in projection


def test_head_supports_without_advice_when_user_rejects_moralizing() -> None:
    state = build_state("我好累，不想听大道理")

    assert state.decision.action == HeadAction.SUPPORT
    assert state.communication.primary_act == CommunicationAct.EMOTIONAL_SUPPORT
    assert CommunicationAct.AVOID_ADVICE in state.communication.secondary_acts
    assert state.communication.turn_policy.advice_budget == 0
    assert state.communication.turn_policy.question_budget == 0
    assert "不提供建议" in state.decision.objective


def test_head_treats_withdrawal_as_a_hypothesis_not_a_fact() -> None:
    state = build_state("算了，当我没说。")
    projection = render_head_projection(state)

    assert state.decision.action == HeadAction.SUPPORT
    assert state.communication.primary_act == CommunicationAct.TOPIC_WITHDRAWAL
    assert state.communication.hypotheses[0].needs_confirmation is True
    assert state.communication.hypotheses[0].confidence < 0.5
    assert "假设不是事实" in projection
    assert "不要断言用户情绪" in state.decision.objective


def test_head_uses_a_minimal_listening_turn_for_low_information_input() -> None:
    state = build_state("嗯")

    assert state.communication.primary_act == CommunicationAct.ACKNOWLEDGE
    assert state.communication.turn_policy.response_length == "very_short"
    assert state.communication.turn_policy.initiative == "listen"
    assert state.communication.turn_policy.question_budget == 0


def test_head_keeps_technical_work_task_scaled() -> None:
    state = build_state("继续优化这个项目的 HeadCore")

    assert state.decision.action == HeadAction.CONTINUE_TASK
    assert state.communication.turn_policy.response_length == "task_scaled"
    assert state.communication.turn_policy.initiative == "solve"
    assert state.communication.turn_policy.advice_budget == 2


def test_head_events_restore_an_active_task(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="user",
            content="开始开发这个项目的 HeadCore 状态事件",
        )
    )
    state = build_state("开始开发这个项目的 HeadCore 状态事件")
    asyncio.run(
        record_head_events(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=message,
            state=state,
            previous=HeadEventContext(),
            allow_write=True,
        )
    )

    restored = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    assert restored.active_task == state.active_task


def test_head_events_respect_memory_write_boundary(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="user",
            content="开始开发这个项目的 HeadCore",
        )
    )
    asyncio.run(
        record_head_events(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=message,
            state=build_state("开始开发这个项目的 HeadCore"),
            previous=HeadEventContext(),
            allow_write=False,
        )
    )

    restored = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    assert restored == HeadEventContext()


def test_head_question_event_is_consumed_by_the_next_user_turn(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    assistant = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="assistant",
            content="报错第一行是什么？",
        )
    )
    asyncio.run(
        record_head_response_event(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=assistant,
            state=build_state("这个报错怎么解决？"),
            allow_write=True,
        )
    )
    previous = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    assert previous.pending_question == "报错第一行是什么？"

    user_message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="user",
            content="第一行是 TypeError",
        )
    )
    asyncio.run(
        record_head_events(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=user_message,
            state=build_state("第一行是 TypeError"),
            previous=previous,
            allow_write=True,
        )
    )
    current = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    assert current.pending_question == "none"


def test_head_feedback_attributes_advice_rejection_to_previous_action(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    assistant = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="assistant",
            content="可以先列三个解决步骤。",
        )
    )
    previous_state = build_state("我该怎么办？")
    asyncio.run(
        record_head_response_event(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=assistant,
            state=previous_state,
            allow_write=True,
        )
    )
    previous = asyncio.run(load_head_event_context(repository, user_id="user-1"))

    conversation = build_conversation_state(user_input="别建议，听我说", recent_messages=[])
    social = build_social_state(
        relationship=DEFAULT_RELATIONSHIP_CONTEXT,
        conversation=conversation,
        recent_messages=[],
        user_input="别建议，听我说",
    )
    state = build_head_state(
        subject_id="user-1",
        user_input="别建议，听我说",
        relationship_role=DEFAULT_RELATIONSHIP_CONTEXT.role,
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=social,
        recent_messages=[],
        event_context=previous,
    )

    assert state.feedback.outcome.value == "advice_rejected"
    assert state.feedback.previous_action == previous_state.decision.action.value
    assert state.feedback.reflection is not None
    assert state.feedback.reflection.mistake_type == "premature_advice"
    assert "单次反馈写成永久用户偏好" in render_head_projection(state)


def test_head_feedback_is_not_inferred_without_a_previous_action() -> None:
    state = build_state("谢谢，这就对了")

    assert state.feedback.outcome.value == "unknown"
    assert state.feedback.previous_action == "none"
    assert state.feedback.reflection is None


def test_head_feedback_events_respect_write_boundary(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    assistant = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="assistant",
            content="先做第一步。",
        )
    )
    asyncio.run(
        record_head_response_event(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=assistant,
            state=build_state("继续开发项目"),
            allow_write=False,
        )
    )

    assert asyncio.run(load_head_event_context(repository, user_id="user-1")) == HeadEventContext()


def test_frequent_action_events_do_not_evict_the_active_task(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    asyncio.run(
        repository.save_memory(
            user_id="user-1",
            session_id=session.id,
            memory_type="head_task",
            content="继续开发 HeadCore",
            confidence=1.0,
        )
    )
    for index in range(20):
        asyncio.run(
            repository.save_memory(
                user_id="user-1",
                session_id=session.id,
                memory_type="head_last_action",
                content=f'{{"action":"answer","sequence":{index}}}',
                confidence=1.0,
            )
        )

    restored = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    assert restored.active_task == "继续开发 HeadCore"
    assert '"sequence":19' in restored.last_action


def test_internal_head_events_are_hidden_from_default_memory_listing(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    asyncio.run(
        repository.save_memory(
            user_id="user-1",
            session_id="s1",
            memory_type="user_preference",
            content="回复简短",
        )
    )
    asyncio.run(
        repository.save_memory(
            user_id="user-1",
            session_id="s1",
            memory_type="head_last_action",
            content='{"action":"answer"}',
        )
    )

    visible = asyncio.run(repository.list_memories(user_id="user-1", limit=8))
    internal = asyncio.run(
        repository.list_memories(
            user_id="user-1",
            memory_types=["head_last_action"],
            limit=1,
        )
    )
    assert [item.memory_type for item in visible] == ["user_preference"]
    assert [item.memory_type for item in internal] == ["head_last_action"]


def feedback_event(outcome: str, created_at: dt.datetime) -> HeadEventRecord:
    return HeadEventRecord(
        content=json.dumps({"outcome": outcome}),
        created_at=created_at.isoformat(),
    )


def test_adaptive_policy_requires_repeated_feedback() -> None:
    now = dt.datetime(2026, 7, 22, tzinfo=dt.UTC)
    policy = build_adaptive_policy(
        feedback_events=(feedback_event("advice_rejected", now),),
        current_feedback=build_state("普通聊天").feedback,
        policy_reset_at=None,
        user_input="普通聊天",
        now=now,
    )

    assert policy.active is False
    assert policy.evidence_count == 0


def test_repeated_advice_rejection_activates_a_temporary_budget_cap() -> None:
    now = dt.datetime(2026, 7, 22, tzinfo=dt.UTC)
    context = HeadEventContext(
        last_action='{"action":"answer"}',
        feedback_events=(feedback_event("advice_rejected", now - dt.timedelta(hours=1)),),
    )
    conversation = build_conversation_state(user_input="别建议，先听我说", recent_messages=[])
    state = build_head_state(
        subject_id="user-1",
        user_input="别建议，先听我说",
        relationship_role=DEFAULT_RELATIONSHIP_CONTEXT.role,
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=build_social_state(
            relationship=DEFAULT_RELATIONSHIP_CONTEXT,
            conversation=conversation,
            recent_messages=[],
            user_input="别建议，先听我说",
        ),
        recent_messages=[],
        event_context=context,
        now=now,
    )

    assert state.feedback.outcome == FeedbackOutcome.ADVICE_REJECTED
    assert state.adaptive_policy.active is True
    assert state.adaptive_policy.advice_budget_cap == 0
    assert state.communication.turn_policy.advice_budget == 0
    assert "adaptive_no_unsolicited_advice" in state.communication.turn_policy.constraints


def test_adaptive_policy_ignores_expired_feedback() -> None:
    now = dt.datetime(2026, 7, 22, tzinfo=dt.UTC)
    policy = build_adaptive_policy(
        feedback_events=(
            feedback_event("corrected", now - dt.timedelta(days=8)),
            feedback_event("corrected", now - dt.timedelta(days=9)),
        ),
        current_feedback=build_state("普通聊天").feedback,
        policy_reset_at=None,
        user_input="普通聊天",
        now=now,
    )

    assert policy.active is False


def test_adaptive_policy_reset_excludes_older_feedback() -> None:
    now = dt.datetime(2026, 7, 22, tzinfo=dt.UTC)
    policy = build_adaptive_policy(
        feedback_events=(
            feedback_event("advice_rejected", now - dt.timedelta(hours=3)),
            feedback_event("advice_rejected", now - dt.timedelta(hours=2)),
        ),
        current_feedback=build_state("普通聊天").feedback,
        policy_reset_at=(now - dt.timedelta(hours=1)).isoformat(),
        user_input="普通聊天",
        now=now,
    )

    assert policy.active is False


def test_explicit_reset_request_disables_policy_immediately() -> None:
    now = dt.datetime(2026, 7, 22, tzinfo=dt.UTC)
    policy = build_adaptive_policy(
        feedback_events=(
            feedback_event("advice_rejected", now - dt.timedelta(hours=2)),
            feedback_event("advice_rejected", now - dt.timedelta(hours=1)),
        ),
        current_feedback=build_state("普通聊天").feedback,
        policy_reset_at=None,
        user_input="恢复默认沟通策略",
        now=now,
    )

    assert policy.active is False


def test_policy_reset_event_is_persisted_and_restored(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    user_message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="user",
            content="恢复默认沟通策略",
        )
    )
    asyncio.run(
        record_head_events(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=user_message,
            state=build_state("恢复默认沟通策略"),
            previous=HeadEventContext(),
            allow_write=True,
        )
    )

    restored = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    assert restored.policy_reset_at == user_message.created_at


def test_ordinary_casual_chat_keeps_a_single_low_latency_action() -> None:
    state = build_state("今天吃什么")

    assert state.plan.complex_scene is False
    assert len(state.plan.candidates) == 1
    assert state.plan.selected_index == 0


def test_complex_technical_task_compares_multiple_actions() -> None:
    state = build_state("继续优化这个项目的 HeadCore，并检查状态恢复和反馈逻辑")

    assert state.plan.complex_scene is True
    assert 2 <= len(state.plan.candidates) <= 4
    assert state.decision == selected_decision(state.plan)
    assert any(candidate.action == HeadAction.CONTINUE_TASK for candidate in state.plan.candidates)
    assert "行动规划=复杂场景:True" in render_head_projection(state)


def test_ambiguous_complex_request_prefers_clarification_over_fabrication() -> None:
    state = build_state("这个怎么做？")

    assert state.plan.complex_scene is True
    assert state.decision.action == HeadAction.CLARIFY
    selected = state.plan.candidates[state.plan.selected_index]
    assert selected.score.fabrication_risk <= 0.02


def test_emotional_no_advice_plan_penalizes_direct_advice() -> None:
    state = build_state("我今天真的很累，不想听大道理，只想说一会儿")

    assert state.plan.complex_scene is True
    assert state.decision.action == HeadAction.SUPPORT
    advice_candidates = [
        candidate
        for candidate in state.plan.candidates
        if candidate.reason == "candidate_direct_advice"
    ]
    assert advice_candidates == []


def test_blocked_relationship_does_not_expand_candidate_search() -> None:
    conversation = build_conversation_state(user_input="帮我设计复杂项目", recent_messages=[])
    state = build_head_state(
        subject_id="blocked-user",
        user_input="帮我设计复杂项目",
        relationship_role="blocked",
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=build_social_state(
            relationship=replace(DEFAULT_RELATIONSHIP_CONTEXT, role="blocked"),
            conversation=conversation,
            recent_messages=[],
            user_input="帮我设计复杂项目",
        ),
        recent_messages=[],
    )

    assert state.decision.action == HeadAction.REFUSE
    assert state.plan.complex_scene is False
    assert len(state.plan.candidates) == 1
