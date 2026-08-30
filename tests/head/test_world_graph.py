from __future__ import annotations

from app.head.contracts import (
    CognitiveFact,
    CognitiveFactKind,
    CognitiveFactSourceKind,
    CognitiveFactStatus,
)
from app.head.world_model_store import (
    MAX_DERIVED_FACTS,
    append_conversation_world_event,
    decode_head_world_model,
    derive_head_world_model,
    encode_head_world_model,
    merge_head_world_models,
)
from app.head.contracts import HeadWorldModel, WorldEntity, WorldEvent


def _weather_fact(field: str, value: str, *, fact_id: str, confidence: float = 0.95) -> CognitiveFact:
    return CognitiveFact(
        fact_id=fact_id,
        key=f"weather.440100.{field}",
        value=value,
        source_id="amap",
        observed_at="2026-08-30T00:00:00+00:00",
        expires_at="2026-08-30T03:00:00+00:00",
        confidence=confidence,
        kind=CognitiveFactKind.OBSERVATION,
        source_kind=CognitiveFactSourceKind.WORLD_EVIDENCE,
        supporting_source_ids=("amap",),
    )


def test_derive_head_world_model_builds_entities_and_relations() -> None:
    facts = [
        _weather_fact("temperature_c", "26", fact_id="world-t"),
        _weather_fact("humidity_percent", "80", fact_id="world-h"),
        _weather_fact("condition", "中雨", fact_id="world-c"),
    ]

    model = derive_head_world_model(facts)

    entity_ids = {entity.entity_id for entity in model.entities}
    assert "loc.weather.440100" in entity_ids
    assert len(model.entities) == 4  # one subject + three values
    assert len(model.relations) == 3
    predicates = {relation.predicate for relation in model.relations}
    assert predicates == {"temperature_c", "humidity_percent", "condition"}
    for relation in model.relations:
        assert relation.subject_id == "loc.weather.440100"
        assert relation.source_id == "amap"


def test_derive_head_world_model_excludes_non_world_evidence() -> None:
    facts = [
        _weather_fact("condition", "中雨", fact_id="world-c"),
        CognitiveFact(
            fact_id="user-1",
            key="weather.440100.temperature_c",
            value="30",
            source_id="user",
            observed_at="2026-08-30T00:00:00+00:00",
            expires_at="2026-08-30T03:00:00+00:00",
            confidence=0.99,
            kind=CognitiveFactKind.OBSERVATION,
            source_kind=CognitiveFactSourceKind.USER_REPORT,
            supporting_source_ids=("user",),
        ),
    ]

    model = derive_head_world_model(facts)

    assert len(model.relations) == 1


def test_derive_head_world_model_is_bounded_and_round_trips() -> None:
    facts = [
        _weather_fact(f"field_{index}", str(index), fact_id=f"world-{index}")
        for index in range(MAX_DERIVED_FACTS * 2)
    ]

    model = derive_head_world_model(facts)

    assert len(model.relations) <= MAX_DERIVED_FACTS
    assert len(model.entities) <= MAX_DERIVED_FACTS * 2

    decoded = decode_head_world_model(encode_head_world_model(model))
    assert decoded.relations == model.relations
    assert decoded.entities == model.entities


def test_derive_head_world_model_ignores_conflicted_facts() -> None:
    fact = _weather_fact("condition", "中雨", fact_id="world-c")
    conflicted = CognitiveFact(
        fact_id=fact.fact_id,
        key=fact.key,
        value=fact.value,
        source_id=fact.source_id,
        observed_at=fact.observed_at,
        expires_at=fact.expires_at,
        confidence=fact.confidence,
        status=CognitiveFactStatus.CONFLICTED,
        kind=CognitiveFactKind.OBSERVATION,
        source_kind=CognitiveFactSourceKind.WORLD_EVIDENCE,
        supporting_source_ids=("amap",),
    )

    model = derive_head_world_model([conflicted])

    assert model.relations == ()
    assert model.entities == ()


def test_merge_head_world_models_preserves_graph_fragments() -> None:
    entity = WorldEntity("service", "service", "Core")
    event = WorldEvent(
        event_id="event-1",
        event_type="deployment",
        actor_ids=("service",),
        occurred_at="2026-08-30T00:00:00+00:00",
        source_id="test",
        summary="deployed",
        confidence=0.9,
    )
    merged = merge_head_world_models(
        HeadWorldModel(entities=(entity,)),
        HeadWorldModel(entities=(entity,), events=(event,)),
    )

    assert merged.entities == (entity,)
    assert merged.events == (event,)


def test_append_conversation_world_event_is_stable_and_bounded() -> None:
    first = append_conversation_world_event(
        HeadWorldModel(),
        user_id="user-1",
        session_id="session-1",
        source_message_id="message-1",
        summary="  a user report  ",
        occurred_at="2026-08-30T00:00:00+00:00",
    )
    second = append_conversation_world_event(
        first,
        user_id="user-1",
        session_id="session-1",
        source_message_id="message-1",
        summary="a user report",
        occurred_at="2026-08-30T00:00:00+00:00",
    )

    assert len(first.entities) == 1
    assert len(first.events) == 1
    assert second == first
    assert first.events[0].source_id == "conversation"
