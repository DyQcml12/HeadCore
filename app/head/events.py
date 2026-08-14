from __future__ import annotations

from app.head.adaptation import is_policy_reset_request
from app.head.contracts import (
    FeedbackOutcome,
    HeadEpisodeKind,
    HeadEventContext,
    HeadEventRecord,
    HeadState,
)
from app.head.episodic_memory import load_episodic_events, save_episodic_event
from app.head.feedback import encode_head_action, encode_head_feedback
from app.head.cognitive_facts import load_cognitive_facts
from app.head.world_model_store import load_head_world_model
from app.head.long_term_plan_store import load_long_term_plan
from app.storage.chat_repository import ChatRepository, MessageRecord


HEAD_EVENT_MEMORY_TYPES = (
    "head_task",
    "head_pending_question",
    "head_last_action",
    "head_feedback",
    "head_policy_reset",
)
EPISODIC_FEEDBACK_OUTCOMES = {
    FeedbackOutcome.CORRECTED,
    FeedbackOutcome.ADVICE_REJECTED,
    FeedbackOutcome.STOPPED,
}


async def load_head_event_context(
    repository: ChatRepository,
    *,
    user_id: str,
) -> HeadEventContext:
    latest_by_type: dict[str, str] = {}
    feedback_records = []
    for memory_type in HEAD_EVENT_MEMORY_TYPES:
        records = await repository.list_memories(
            user_id=user_id,
            memory_types=[memory_type],
            limit=12 if memory_type == "head_feedback" else 1,
        )
        if records:
            latest_by_type[memory_type] = records[-1].content
        if memory_type == "head_feedback":
            feedback_records = records
    return HeadEventContext(
        active_task=latest_by_type.get("head_task", "none"),
        pending_question=latest_by_type.get("head_pending_question", "none"),
        last_action=latest_by_type.get("head_last_action", "none"),
        last_feedback=latest_by_type.get("head_feedback", "none"),
        feedback_events=tuple(
            HeadEventRecord(content=record.content, created_at=record.created_at)
            for record in feedback_records
        ),
        episodic_events=await load_episodic_events(repository, user_id=user_id),
        policy_reset_at=(
            latest_by_type.get("head_policy_reset")
            if "head_policy_reset" in latest_by_type
            else None
        ),
        cognitive_facts=await load_cognitive_facts(repository, user_id=user_id),
        world_model=await load_head_world_model(repository, user_id=user_id),
        long_term_plan=await load_long_term_plan(repository, user_id=user_id),
    )


async def record_head_events(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message: MessageRecord,
    state: HeadState,
    previous: HeadEventContext,
    allow_write: bool,
) -> None:
    if not allow_write:
        return
    if state.active_task != "none" and state.active_task != previous.active_task:
        await repository.save_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type="head_task",
            content=state.active_task,
            source_message_id=source_message.id,
            confidence=0.8,
        )
        await save_episodic_event(
            repository,
            user_id=user_id,
            session_id=session_id,
            source_message_id=source_message.id,
            kind=(
                HeadEpisodeKind.TASK_STARTED
                if previous.active_task == "none"
                else HeadEpisodeKind.TASK_UPDATED
            ),
            summary=state.active_task,
            occurred_at=source_message.created_at,
            allow_write=True,
        )
    if previous.pending_question != "none":
        await repository.save_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type="head_pending_question",
            content="none",
            source_message_id=source_message.id,
            confidence=1.0,
        )
        await save_episodic_event(
            repository,
            user_id=user_id,
            session_id=session_id,
            source_message_id=source_message.id,
            kind=HeadEpisodeKind.QUESTION_ANSWERED,
            summary=previous.pending_question,
            occurred_at=source_message.created_at,
            allow_write=True,
        )
    if state.feedback.outcome != FeedbackOutcome.UNKNOWN:
        await repository.save_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type="head_feedback",
            content=encode_head_feedback(state.feedback),
            source_message_id=source_message.id,
            confidence=1.0,
        )
        if state.feedback.outcome in EPISODIC_FEEDBACK_OUTCOMES:
            await save_episodic_event(
                repository,
                user_id=user_id,
                session_id=session_id,
                source_message_id=source_message.id,
                kind=HeadEpisodeKind.FEEDBACK_RECEIVED,
                summary=state.feedback.outcome.value,
                occurred_at=source_message.created_at,
                allow_write=True,
            )
    if is_policy_reset_request(source_message.content):
        await repository.save_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type="head_policy_reset",
            content=source_message.created_at,
            source_message_id=source_message.id,
            confidence=1.0,
        )


async def record_head_response_event(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message: MessageRecord,
    state: HeadState,
    allow_write: bool,
) -> None:
    if not allow_write:
        return
    question = source_message.content.strip()
    if question.endswith(("?", "？")):
        await repository.save_memory(
            user_id=user_id,
            session_id=session_id,
            memory_type="head_pending_question",
            content=question[-80:],
            source_message_id=source_message.id,
            confidence=1.0,
        )
        await save_episodic_event(
            repository,
            user_id=user_id,
            session_id=session_id,
            source_message_id=source_message.id,
            kind=HeadEpisodeKind.QUESTION_ASKED,
            summary=question,
            occurred_at=source_message.created_at,
            allow_write=True,
        )
    await repository.save_memory(
        user_id=user_id,
        session_id=session_id,
        memory_type="head_last_action",
        content=encode_head_action(
            action=state.decision.action.value,
            reason=state.decision.reason,
            advice_budget=state.communication.turn_policy.advice_budget,
        ),
        source_message_id=source_message.id,
        confidence=1.0,
    )
