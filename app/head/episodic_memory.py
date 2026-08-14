from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import asdict
from typing import Iterable

from app.head.contracts import HeadEpisodeKind, HeadEpisodicEvent
from app.storage.chat_repository import ChatRepository


EPISODE_MEMORY_TYPE = "head_episode"
MAX_EPISODES_PER_USER = 12
MAX_WORKING_MEMORY_EVENTS = 4


def encode_episodic_event(event: HeadEpisodicEvent) -> str:
    _validate_event(event)
    payload = asdict(event)
    payload["kind"] = event.kind.value
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_episodic_event(content: str) -> HeadEpisodicEvent:
    try:
        payload = json.loads(content)
        event = HeadEpisodicEvent(
            event_id=str(payload["event_id"]),
            kind=HeadEpisodeKind(str(payload["kind"])),
            summary=str(payload["summary"]),
            occurred_at=str(payload["occurred_at"]),
            source_message_id=str(payload["source_message_id"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid episodic event") from exc
    _validate_event(event)
    return event


async def save_episodic_event(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str,
    kind: HeadEpisodeKind,
    summary: str,
    occurred_at: str,
    allow_write: bool,
) -> None:
    if not allow_write:
        return
    event = HeadEpisodicEvent(
        event_id=str(uuid.uuid4()),
        kind=kind,
        summary=_compact(summary),
        occurred_at=occurred_at,
        source_message_id=source_message_id,
    )
    await repository.save_memory(
        user_id=user_id,
        session_id=session_id,
        memory_type=EPISODE_MEMORY_TYPE,
        content=encode_episodic_event(event),
        source_message_id=source_message_id,
        confidence=1.0,
    )


async def load_episodic_events(
    repository: ChatRepository,
    *,
    user_id: str,
) -> tuple[HeadEpisodicEvent, ...]:
    records = await repository.list_memories(
        user_id=user_id,
        memory_types=[EPISODE_MEMORY_TYPE],
        limit=MAX_EPISODES_PER_USER,
    )
    events: list[HeadEpisodicEvent] = []
    for record in records:
        try:
            events.append(decode_episodic_event(record.content))
        except ValueError:
            continue
    return tuple(events)


def project_working_memory(
    events: Iterable[HeadEpisodicEvent],
    *,
    limit: int = MAX_WORKING_MEMORY_EVENTS,
) -> tuple[str, ...]:
    if limit <= 0:
        return ()
    recent = tuple(events)[-limit:]
    return tuple(f"近期经历[{event.kind.value}]={event.summary}" for event in recent)


def _validate_event(event: HeadEpisodicEvent) -> None:
    if not event.event_id.strip() or len(event.event_id) > 96:
        raise ValueError("episodic event_id must be a bounded identifier")
    if not event.source_message_id.strip() or len(event.source_message_id) > 96:
        raise ValueError("episodic source_message_id must be a bounded identifier")
    if not event.summary.strip() or len(event.summary) > 160:
        raise ValueError("episodic summary must contain 1 to 160 characters")
    if any(character in event.summary for character in "\r\n\x00"):
        raise ValueError("episodic summary must be a single line")
    _parse_time(event.occurred_at)


def _parse_time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("episodic occurred_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("episodic occurred_at must include a timezone")
    return parsed.astimezone(dt.UTC)


def _compact(value: str, limit: int = 160) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"
