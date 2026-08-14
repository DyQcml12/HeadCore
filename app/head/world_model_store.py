from __future__ import annotations

import json
from dataclasses import asdict

from app.head.contracts import (
    CausalHypothesis,
    HeadWorldModel,
    WorldEntity,
    WorldEvent,
    WorldRelation,
)
from app.head.world_model import build_head_world_model
from app.storage.chat_repository import ChatRepository


WORLD_MODEL_MEMORY_TYPE = "head_world_model"
WORLD_MODEL_SCHEMA_VERSION = 1
MAX_ENTITIES = 64
MAX_RELATIONS = 128
MAX_EVENTS = 128
MAX_HYPOTHESES = 64


def encode_head_world_model(model: HeadWorldModel) -> str:
    _validate_size(model)
    return json.dumps(
        {
            "schema_version": WORLD_MODEL_SCHEMA_VERSION,
            "entities": [asdict(item) for item in model.entities],
            "relations": [asdict(item) for item in model.relations],
            "events": [asdict(item) for item in model.events],
            "causal_hypotheses": [asdict(item) for item in model.causal_hypotheses],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_head_world_model(content: str) -> HeadWorldModel:
    try:
        payload = json.loads(content)
        if payload.get("schema_version") != WORLD_MODEL_SCHEMA_VERSION:
            raise ValueError("unsupported head world model schema")
        entities = tuple(WorldEntity(**item) for item in payload.get("entities", []))
        relations = tuple(
            WorldRelation(
                relation_id=item["relation_id"],
                subject_id=item["subject_id"],
                predicate=item["predicate"],
                object_id=item["object_id"],
                source_id=item["source_id"],
                valid_from=item["valid_from"],
                valid_until=item.get("valid_until"),
                confidence=float(item["confidence"]),
            )
            for item in payload.get("relations", [])
        )
        events = tuple(
            WorldEvent(
                event_id=item["event_id"],
                event_type=item["event_type"],
                actor_ids=tuple(item["actor_ids"]),
                occurred_at=item["occurred_at"],
                source_id=item["source_id"],
                summary=item["summary"],
                confidence=float(item["confidence"]),
            )
            for item in payload.get("events", [])
        )
        hypotheses = tuple(
            CausalHypothesis(
                hypothesis_id=item["hypothesis_id"],
                cause_event_id=item["cause_event_id"],
                effect_event_id=item["effect_event_id"],
                rationale=item["rationale"],
                confidence=float(item["confidence"]),
                evidence_ids=tuple(item["evidence_ids"]),
                confirmed=bool(item.get("confirmed", False)),
            )
            for item in payload.get("causal_hypotheses", [])
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid persisted head world model") from exc
    model = build_head_world_model(
        entities=entities,
        relations=relations,
        events=events,
        causal_hypotheses=hypotheses,
    )
    _validate_size(model)
    return model


async def save_head_world_model(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str | None,
    model: HeadWorldModel,
    allow_write: bool,
) -> None:
    if not allow_write:
        return
    await repository.save_memory(
        user_id=user_id,
        session_id=session_id,
        memory_type=WORLD_MODEL_MEMORY_TYPE,
        content=encode_head_world_model(model),
        source_message_id=source_message_id,
        confidence=1.0,
    )


async def load_head_world_model(
    repository: ChatRepository,
    *,
    user_id: str,
) -> HeadWorldModel:
    records = await repository.list_memories(
        user_id=user_id,
        memory_types=[WORLD_MODEL_MEMORY_TYPE],
        limit=4,
    )
    for record in reversed(records):
        try:
            return decode_head_world_model(record.content)
        except ValueError:
            continue
    return HeadWorldModel()


def _validate_size(model: HeadWorldModel) -> None:
    limits = (
        (len(model.entities), MAX_ENTITIES, "entities"),
        (len(model.relations), MAX_RELATIONS, "relations"),
        (len(model.events), MAX_EVENTS, "events"),
        (len(model.causal_hypotheses), MAX_HYPOTHESES, "causal hypotheses"),
    )
    for count, limit, label in limits:
        if count > limit:
            raise ValueError(f"head world model exceeds {label} limit")
