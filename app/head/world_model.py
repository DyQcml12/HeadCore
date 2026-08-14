from __future__ import annotations

import datetime as dt
import re
from dataclasses import replace
from typing import Iterable

from app.head.contracts import (
    CausalHypothesis,
    HeadWorldModel,
    WorldAssertionStatus,
    WorldEntity,
    WorldEvent,
    WorldRelation,
)

DEFAULT_EVENT_CONTEXT_MAX_AGE = dt.timedelta(days=30)


def build_head_world_model(
    *,
    entities: Iterable[WorldEntity] = (),
    relations: Iterable[WorldRelation] = (),
    events: Iterable[WorldEvent] = (),
    causal_hypotheses: Iterable[CausalHypothesis] = (),
    now: dt.datetime | None = None,
) -> HeadWorldModel:
    current_time = _aware(now or dt.datetime.now(dt.UTC))
    entity_items = tuple(sorted(entities, key=lambda item: item.entity_id))
    entity_ids = {item.entity_id for item in entity_items}
    if len(entity_ids) != len(entity_items):
        raise ValueError("duplicate world entity_id")
    for entity in entity_items:
        _validate_identifier(entity.entity_id, "entity_id")
        _validate_identifier(entity.entity_type, "entity_type")
        _validate_text(entity.name, "entity name", limit=120)

    relation_items = [_resolve_relation(item, current_time, entity_ids) for item in relations]
    relation_items = _mark_relation_conflicts(relation_items)
    event_items = tuple(sorted((_validate_event(item, entity_ids) for item in events), key=_event_time))
    event_ids = {item.event_id for item in event_items}
    if len(event_ids) != len(event_items):
        raise ValueError("duplicate world event_id")
    hypothesis_items = tuple(
        sorted(
            (_validate_hypothesis(item, event_ids) for item in causal_hypotheses),
            key=lambda item: item.hypothesis_id,
        )
    )
    uncertainties = [
        f"关系冲突:{item.subject_id}.{item.predicate}"
        for item in relation_items
        if item.status == WorldAssertionStatus.CONFLICTED
    ]
    uncertainties.extend(
        f"因果待验证:{item.hypothesis_id}" for item in hypothesis_items if not item.confirmed
    )
    stale_event_types = {
        item.event_type
        for item in event_items
        if _event_time(item) < current_time - DEFAULT_EVENT_CONTEXT_MAX_AGE
    }
    uncertainties.extend(f"world_event_stale:{event_type}" for event_type in sorted(stale_event_types))
    return HeadWorldModel(
        entities=entity_items,
        relations=tuple(sorted(relation_items, key=lambda item: item.relation_id)),
        events=event_items,
        causal_hypotheses=hypothesis_items,
        uncertainties=tuple(dict.fromkeys(uncertainties)),
    )


def project_head_world_model(
    model: HeadWorldModel,
    *,
    limit: int = 8,
    now: dt.datetime | None = None,
    event_max_age: dt.timedelta = DEFAULT_EVENT_CONTEXT_MAX_AGE,
) -> tuple[str, ...]:
    current_time = _aware(now or dt.datetime.now(dt.UTC))
    if event_max_age <= dt.timedelta():
        raise ValueError("event_max_age must be positive")
    names = {entity.entity_id: entity.name for entity in model.entities}
    values: list[str] = []
    for relation in model.relations:
        if relation.status != WorldAssertionStatus.ACTIVE:
            continue
        values.append(
            f"世界关系={names[relation.subject_id]}|{relation.predicate}|{names[relation.object_id]};"
            f"source={relation.source_id};confidence={relation.confidence:.2f}"
        )
    for event in reversed(model.events):
        if _event_time(event) < current_time - event_max_age:
            continue
        values.append(
            f"世界事件={event.summary};occurred_at={event.occurred_at};"
            f"source={event.source_id};confidence={event.confidence:.2f}"
        )
    for hypothesis in model.causal_hypotheses:
        label = "已确认因果" if hypothesis.confirmed else "因果假设(不得当作事实)"
        values.append(f"{label}={hypothesis.rationale};confidence={hypothesis.confidence:.2f}")
    return tuple(values[:limit])


def _resolve_relation(relation: WorldRelation, now: dt.datetime, entity_ids: set[str]) -> WorldRelation:
    _validate_identifier(relation.relation_id, "relation_id")
    _validate_identifier(relation.predicate, "predicate")
    _require_entities((relation.subject_id, relation.object_id), entity_ids)
    _validate_source_and_confidence(relation.source_id, relation.confidence)
    valid_from = _parse_time(relation.valid_from)
    valid_until = _parse_time(relation.valid_until) if relation.valid_until else None
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("world relation valid_until must follow valid_from")
    return replace(
        relation,
        status=(
            WorldAssertionStatus.STALE
            if valid_until is not None and valid_until <= now
            else WorldAssertionStatus.ACTIVE
        ),
    )


def _mark_relation_conflicts(relations: list[WorldRelation]) -> list[WorldRelation]:
    active_objects: dict[tuple[str, str], set[str]] = {}
    for relation in relations:
        if relation.status == WorldAssertionStatus.ACTIVE:
            active_objects.setdefault((relation.subject_id, relation.predicate), set()).add(
                relation.object_id
            )
    conflicts = {key for key, values in active_objects.items() if len(values) > 1}
    return [
        replace(relation, status=WorldAssertionStatus.CONFLICTED)
        if relation.status == WorldAssertionStatus.ACTIVE
        and (relation.subject_id, relation.predicate) in conflicts
        else relation
        for relation in relations
    ]


def _validate_event(event: WorldEvent, entity_ids: set[str]) -> WorldEvent:
    _validate_identifier(event.event_id, "event_id")
    _validate_identifier(event.event_type, "event_type")
    if not event.actor_ids:
        raise ValueError("world event requires at least one actor")
    _require_entities(event.actor_ids, entity_ids)
    _parse_time(event.occurred_at)
    _validate_source_and_confidence(event.source_id, event.confidence)
    _validate_text(event.summary, "event summary", limit=240)
    return event


def _validate_hypothesis(hypothesis: CausalHypothesis, event_ids: set[str]) -> CausalHypothesis:
    _validate_identifier(hypothesis.hypothesis_id, "hypothesis_id")
    missing = {hypothesis.cause_event_id, hypothesis.effect_event_id} - event_ids
    if missing:
        raise ValueError(f"causal hypothesis references unknown event: {sorted(missing)}")
    if hypothesis.cause_event_id == hypothesis.effect_event_id:
        raise ValueError("causal hypothesis cause and effect must differ")
    _validate_text(hypothesis.rationale, "causal rationale", limit=240)
    if not 0.0 <= hypothesis.confidence <= 1.0:
        raise ValueError("causal hypothesis confidence must be between 0 and 1")
    if hypothesis.confirmed and (hypothesis.confidence < 0.8 or not hypothesis.evidence_ids):
        raise ValueError("confirmed causal hypothesis requires evidence and confidence >= 0.8")
    return hypothesis


def _validate_source_and_confidence(source_id: str, confidence: float) -> None:
    _validate_identifier(source_id, "source_id")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("world assertion confidence must be between 0 and 1")


def _require_entities(values: Iterable[str], entity_ids: set[str]) -> None:
    missing = set(values) - entity_ids
    if missing:
        raise ValueError(f"world assertion references unknown entity: {sorted(missing)}")


def _validate_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,95}", value):
        raise ValueError(f"invalid world {label}")


def _validate_text(value: str, label: str, *, limit: int) -> None:
    if not value.strip() or len(value) > limit or any(char in value for char in "\r\n\x00"):
        raise ValueError(f"{label} must be one bounded line")


def _event_time(event: WorldEvent) -> dt.datetime:
    return _parse_time(event.occurred_at)


def _parse_time(value: str) -> dt.datetime:
    try:
        return _aware(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError("world model timestamp must be ISO-8601") from exc


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise ValueError("world model timestamps must include a timezone")
    return value.astimezone(dt.UTC)
