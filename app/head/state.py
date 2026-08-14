from __future__ import annotations

import datetime as dt

from app.head.adaptation import apply_adaptive_policy, build_adaptive_policy
from app.head.contracts import HeadEventContext, HeadState
from app.head.communication import build_communication_state
from app.head.feedback import build_head_feedback
from app.head.cognitive_facts import project_cognitive_fact_uncertainties, project_cognitive_facts
from app.head.episodic_memory import project_working_memory
from app.head.world_model import project_head_world_model
from app.head.long_term_planning import project_long_term_plan
from app.head.decision import decide_head_action
from app.head.planning import build_head_plan, selected_decision
from app.mind.conversation_state import ConversationState
from app.mind.self_state import SelfState
from app.mind.social_state import SocialState
from app.storage.chat_repository import MessageRecord


def build_head_state(
    *,
    subject_id: str,
    user_input: str,
    relationship_role: str,
    conversation: ConversationState,
    self_state: SelfState,
    social_state: SocialState,
    recent_messages: list[MessageRecord],
    event_context: HeadEventContext = HeadEventContext(),
    additional_uncertainties: tuple[str, ...] = (),
    now: dt.datetime | None = None,
) -> HeadState:
    active_task = _infer_active_task(conversation, recent_messages, event_context.active_task, user_input)
    pending_question = _latest_pending_question(recent_messages, event_context.pending_question)
    long_term_context = (
        project_long_term_plan(event_context.long_term_plan)
        if event_context.long_term_plan is not None
        else ()
    )
    known_context = _known_context(conversation, active_task, pending_question) + project_cognitive_facts(
        event_context.cognitive_facts
    ) + project_working_memory(event_context.episodic_events) + project_head_world_model(
        event_context.world_model
    ) + long_term_context
    plan_uncertainties = (
        (f"长期计划阻塞:{event_context.long_term_plan.plan_id}",)
        if event_context.long_term_plan is not None
        and event_context.long_term_plan.status.value == "blocked"
        else ()
    )
    uncertainties = (
        _infer_uncertainties(user_input)
        + project_cognitive_fact_uncertainties(event_context.cognitive_facts)
        + event_context.world_model.uncertainties
        + plan_uncertainties
        + additional_uncertainties
    )
    uncertainties = tuple(dict.fromkeys(uncertainties))
    feedback = build_head_feedback(
        user_input=user_input,
        previous_action_json=event_context.last_action,
    )
    adaptive_policy = build_adaptive_policy(
        feedback_events=event_context.feedback_events,
        current_feedback=feedback,
        policy_reset_at=event_context.policy_reset_at,
        user_input=user_input,
        now=now,
    )
    communication = apply_adaptive_policy(build_communication_state(
        user_input=user_input,
        conversation=conversation,
        has_active_task=active_task != "none",
    ), adaptive_policy)
    base_decision = decide_head_action(
        user_input=user_input,
        relationship_role=relationship_role,
        conversation=conversation,
        social=social_state,
        active_task=active_task,
        uncertainties=uncertainties,
        communication=communication,
    )
    plan = build_head_plan(
        base_decision=base_decision,
        user_input=user_input,
        current_topic=conversation.current_topic,
        relationship_role=relationship_role,
        active_task=active_task,
        uncertainties=uncertainties,
        communication=communication,
        feedback=feedback,
    )
    decision = selected_decision(plan)
    return HeadState(
        subject_id=subject_id,
        relationship_role=relationship_role,
        current_topic=conversation.current_topic,
        user_state=conversation.recent_user_mood,
        self_mood=self_state.mood,
        social_boundary=social_state.boundary_mode,
        active_task=active_task,
        pending_question=pending_question,
        known_context=known_context,
        uncertainties=uncertainties,
        communication=communication,
        feedback=feedback,
        adaptive_policy=adaptive_policy,
        world_model=event_context.world_model,
        long_term_plan=event_context.long_term_plan,
        plan=plan,
        decision=decision,
    )


def _infer_active_task(
    conversation: ConversationState,
    recent_messages: list[MessageRecord],
    stored_task: str,
    user_input: str,
) -> str:
    if conversation.current_topic != "technical_or_project":
        if stored_task != "none" and any(marker in user_input for marker in ("继续", "接着", "然后", "下一步")):
            return stored_task
        return "none"
    for message in reversed(recent_messages):
        if message.role == "user" and message.content.strip():
            return _compact(message.content)
    return "处理当前技术或项目请求"


def _latest_pending_question(recent_messages: list[MessageRecord], stored_question: str) -> str:
    if not recent_messages:
        return stored_question
    latest = recent_messages[-1]
    if latest.role == "assistant" and latest.content.rstrip().endswith(("?", "？")):
        return _compact(latest.content)
    return stored_question


def _known_context(
    conversation: ConversationState, active_task: str, pending_question: str
) -> tuple[str, ...]:
    values = [f"当前话题={conversation.current_topic}", f"用户状态={conversation.recent_user_mood}"]
    if active_task != "none":
        values.append(f"当前任务={active_task}")
    if pending_question != "none":
        values.append(f"等待用户回答={pending_question}")
    return tuple(values)


def _infer_uncertainties(user_input: str) -> tuple[str, ...]:
    text = user_input.strip()
    if not text:
        return ("用户输入为空",)
    explicit_objects = ("这个项目", "这个问题", "这个接口", "这个模型", "这个文件", "这个报错")
    if (
        len(text) <= 12
        and not any(value in text for value in explicit_objects)
        and any(marker in text for marker in ("这个", "那个", "它", "这样", "那样"))
    ):
        return ("指代对象不明确",)
    return ()


def _compact(text: str, limit: int = 80) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"
