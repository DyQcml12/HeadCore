from __future__ import annotations

from app.head.world_state import (
    WorldKnowledgeStatus,
    build_head_world_state,
    render_head_world_state,
    world_state_uncertainties,
)
from app.world.context import WorldConflict, WorldContextProjection


def test_ready_world_evidence_can_support_an_answer() -> None:
    state = build_head_world_state(
        WorldContextProjection(
            status="ready",
            tool_intent="weather",
            item_count=1,
            source_ids=("amap",),
        )
    )
    assert state.status == WorldKnowledgeStatus.KNOWN
    assert state.can_answer is True
    assert state.requires_clarification is False


def test_missing_location_requires_user_input() -> None:
    state = build_head_world_state(
        WorldContextProjection(status="needs_location", tool_intent="weather")
    )
    assert state.status == WorldKnowledgeStatus.NEEDS_INPUT
    assert state.can_answer is False
    assert state.requires_clarification is True


def test_conflicting_world_evidence_remains_uncertain() -> None:
    state = build_head_world_state(
        WorldContextProjection(
            status="conflicted",
            tool_intent="weather",
            item_count=2,
            source_ids=("source-a", "source-b"),
            conflict_count=1,
            conflicts=(
                WorldConflict(
                    field="temperature",
                    values=("20", "27"),
                    source_ids=("source-a", "source-b"),
                ),
            ),
        )
    )
    assert state.status == WorldKnowledgeStatus.UNCERTAIN
    assert state.can_answer is True
    assert state.conflict_fields == ("temperature",)
    assert "uncertain 必须保留冲突" in render_head_world_state(state)


def test_disabled_world_cannot_claim_realtime_facts() -> None:
    state = build_head_world_state(
        WorldContextProjection(status="disabled", tool_intent="news")
    )
    assert state.status == WorldKnowledgeStatus.UNAVAILABLE
    assert state.can_answer is False
    assert world_state_uncertainties(state) == ("world_evidence_unavailable:news",)


def test_world_state_maps_only_non_ready_states_to_bounded_uncertainties() -> None:
    missing = build_head_world_state(
        WorldContextProjection(status="needs_location", tool_intent="weather_current")
    )
    conflicted = build_head_world_state(
        WorldContextProjection(status="conflicted", tool_intent="weather_current")
    )
    ready = build_head_world_state(
        WorldContextProjection(status="ready", tool_intent="weather_current", item_count=1)
    )

    assert world_state_uncertainties(missing) == ("world_input_required:weather_current",)
    assert world_state_uncertainties(conflicted) == (
        "world_evidence_uncertain:weather_current",
    )
    assert world_state_uncertainties(ready) == ()
