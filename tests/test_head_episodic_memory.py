from __future__ import annotations

import asyncio

from app.head import (
    HeadEventContext,
    build_head_state,
    load_head_event_context,
    record_head_events,
    record_head_response_event,
)
from app.mind.conversation_state import build_conversation_state
from app.mind.self_state import build_self_state
from app.mind.social_state import build_social_state
from app.persona.relationship_context import DEFAULT_RELATIONSHIP_CONTEXT
from app.storage.chat_repository import JsonlChatRepository


def build_state(user_input: str, *, event_context: HeadEventContext = HeadEventContext()):
    conversation = build_conversation_state(user_input=user_input, recent_messages=[])
    return build_head_state(
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
        event_context=event_context,
    )


def test_task_change_creates_user_scoped_episode_and_working_memory(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="user",
            content="开始开发这个项目的 HeadCore 情景时间线",
        )
    )
    state = build_state(message.content)
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
    other_user = asyncio.run(load_head_event_context(repository, user_id="user-2"))

    assert [(item.kind.value, item.source_message_id) for item in restored.episodic_events] == [
        ("task_started", message.id),
    ]
    assert other_user.episodic_events == ()
    next_state = build_state("继续", event_context=restored)
    assert any(
        item.startswith("近期经历[task_started]=") for item in next_state.known_context
    )


def test_question_episode_is_followed_by_answer_episode(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    assistant = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="assistant",
            content="你想先继续人头还是网页？",
        )
    )
    asyncio.run(
        record_head_response_event(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=assistant,
            state=build_state("继续开发"),
            allow_write=True,
        )
    )
    previous = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    user_message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="user",
            content="先继续人头",
        )
    )
    asyncio.run(
        record_head_events(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=user_message,
            state=build_state(user_message.content, event_context=previous),
            previous=previous,
            allow_write=True,
        )
    )

    restored = asyncio.run(load_head_event_context(repository, user_id="user-1"))

    assert [item.kind.value for item in restored.episodic_events] == [
        "question_asked",
        "question_answered",
    ]
    assert restored.episodic_events[-1].source_message_id == user_message.id


def test_episode_history_is_bounded_to_recent_events(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    state = build_state("继续开发")
    for index in range(15):
        assistant = asyncio.run(
            repository.save_message(
                session_id=session.id,
                user_id="user-1",
                role="assistant",
                content=f"第 {index} 个确认问题？",
            )
        )
        asyncio.run(
            record_head_response_event(
                repository,
                user_id="user-1",
                session_id=session.id,
                source_message=assistant,
                state=state,
                allow_write=True,
            )
        )

    restored = asyncio.run(load_head_event_context(repository, user_id="user-1"))

    assert len(restored.episodic_events) == 12
    assert restored.episodic_events[0].summary == "第 3 个确认问题？"
    assert restored.episodic_events[-1].summary == "第 14 个确认问题？"


def test_explicit_feedback_becomes_an_episode_without_becoming_a_preference(tmp_path) -> None:
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
    asyncio.run(
        record_head_response_event(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=assistant,
            state=build_state("这个问题怎么解决？"),
            allow_write=True,
        )
    )
    previous = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    user_message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="user",
            content="别建议，先听我说",
        )
    )
    state = build_state(user_message.content, event_context=previous)
    asyncio.run(
        record_head_events(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message=user_message,
            state=state,
            previous=previous,
            allow_write=True,
        )
    )

    restored = asyncio.run(load_head_event_context(repository, user_id="user-1"))

    assert state.feedback.outcome.value == "advice_rejected"
    assert [item.kind.value for item in restored.episodic_events] == ["feedback_received"]
    assert restored.episodic_events[0].summary == "advice_rejected"
    visible = asyncio.run(repository.list_memories(user_id="user-1", limit=20))
    assert visible == []
