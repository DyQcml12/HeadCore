from __future__ import annotations

import json
import hashlib
import re
import datetime as dt
from dataclasses import asdict
from typing import Iterable

from app.head.contracts import (
    CausalHypothesis,
    CognitiveFact,
    CognitiveFactKind,
    CognitiveFactSourceKind,
    CognitiveFactStatus,
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

MAX_DERIVED_FACTS = 24
_IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,95}")


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


def derive_head_world_model(facts: Iterable[CognitiveFact]) -> HeadWorldModel:
    """Derive a minimal entity/relation graph from resolved cognitive facts.

    Only active, confirmed world-evidence facts participate. Each fact becomes a
    subject entity (capability + location key), a value entity, and one relation
    ``subject --field--> value``. The result is deterministic and bounded so the
    persisted graph never exceeds the size limits enforced by ``encode_head_world_model``.
    """
    from app.head.cognitive_facts import cognitive_fact_strength

    active = [
        fact
        for fact in facts
        if fact.status == CognitiveFactStatus.ACTIVE
        and fact.source_kind == CognitiveFactSourceKind.WORLD_EVIDENCE
        and fact.kind in {CognitiveFactKind.OBSERVATION, CognitiveFactKind.BELIEF}
    ]
    active.sort(key=lambda fact: (-cognitive_fact_strength(fact), fact.key, fact.fact_id))
    entities: dict[str, WorldEntity] = {}
    relations: list[WorldRelation] = []
    for fact in active[:MAX_DERIVED_FACTS]:
        subject_id, predicate = _split_fact_key(fact.key)
        if subject_id is None or predicate is None:
            continue
        capability = fact.key.split(".", 1)[0]
        subject_entity_id = f"loc.{capability}.{subject_id}"
        value_entity_id = f"val.{fact.fact_id}"
        relation_id = f"rel.{fact.fact_id}"
        if not all(
            _IDENTIFIER_RE.fullmatch(value)
            for value in (subject_entity_id, value_entity_id, relation_id)
        ):
            continue
        entities.setdefault(
            subject_entity_id,
            WorldEntity(
                entity_id=subject_entity_id,
                entity_type=capability,
                name=_bounded_text(subject_id),
            ),
        )
        entities.setdefault(
            value_entity_id,
            WorldEntity(
                entity_id=value_entity_id,
                entity_type="value",
                name=_bounded_text(fact.value),
            ),
        )
        relations.append(
            WorldRelation(
                relation_id=relation_id,
                subject_id=subject_entity_id,
                predicate=predicate,
                object_id=value_entity_id,
                source_id=fact.source_id,
                valid_from=fact.observed_at,
                valid_until=fact.expires_at,
                confidence=fact.confidence,
            )
        )
    return build_head_world_model(entities=tuple(entities.values()), relations=relations)


def merge_head_world_models(
    *models: HeadWorldModel,
    now: dt.datetime | None = None,
) -> HeadWorldModel:
    """Merge bounded world-model fragments without dropping existing events.

    Fact projection and conversation events are produced by different stages of
    a turn. Merging by stable identifiers keeps both fragments available while
    allowing the canonical builder to re-evaluate conflicts and staleness.
    """
    entities: dict[str, WorldEntity] = {}
    relations: dict[str, WorldRelation] = {}
    events: dict[str, WorldEvent] = {}
    hypotheses: dict[str, CausalHypothesis] = {}
    for model in models:
        entities.update({item.entity_id: item for item in model.entities})
        relations.update({item.relation_id: item for item in model.relations})
        events.update({item.event_id: item for item in model.events})
        hypotheses.update({item.hypothesis_id: item for item in model.causal_hypotheses})
    return build_head_world_model(
        entities=tuple(entities.values()),
        relations=tuple(relations.values()),
        events=tuple(events.values()),
        causal_hypotheses=tuple(hypotheses.values()),
        now=now,
    )


def append_conversation_world_event(
    model: HeadWorldModel,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str,
    summary: str,
    occurred_at: str,
) -> HeadWorldModel:
    """Add a minimal, provenance-tagged conversation event to the world graph.

    This records that a user turn happened, without converting model text into
    a factual world assertion. The stable digest prevents duplicate events when
    a request is retried.
    """
    user_digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    event_digest = hashlib.sha256(source_message_id.encode("utf-8")).hexdigest()[:24]
    user_entity = WorldEntity(
        entity_id=f"user.{user_digest}",
        entity_type="conversation_user",
        name="conversation user",
    )
    bounded_summary = " ".join(summary.split())[:240] or "conversation turn"
    event = WorldEvent(
        event_id=f"turn.{event_digest}",
        event_type="conversation_turn",
        actor_ids=(user_entity.entity_id,),
        occurred_at=occurred_at,
        source_id="conversation",
        summary=bounded_summary,
        confidence=1.0,
    )
    return merge_head_world_models(
        model,
        HeadWorldModel(entities=(user_entity,), events=(event,)),
    )


def _split_fact_key(key: str) -> tuple[str | None, str | None]:
    parts = key.split(".")
    if len(parts) < 3:
        return None, None
    prefix, field = parts[0], parts[-1]
    subject = ".".join(parts[1:-1])
    if not prefix or not subject or not field:
        return None, None
    if not _IDENTIFIER_RE.fullmatch(field):
        return None, None
    return subject, field


def _bounded_text(value: str, limit: int = 120) -> str:
    text = " ".join(str(value).split())
    return text[:limit]


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
