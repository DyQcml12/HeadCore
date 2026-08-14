from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from app.head.contracts import CausalHypothesis, WorldEvent
from scripts.evaluate_world_model_counterfactuals import evaluate_scenarios
from app.head.world_simulation import (
    TRIAL_STATUS_EXPIRED,
    TRIAL_STATUS_REFUTED,
    TRIAL_STATUS_SUPPORTED,
    CounterfactualTrial,
    decide_trial,
    resolve_counterfactual_trials,
)


NOW = dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC)


def event(event_id: str, event_type: str, occurred_at: str) -> WorldEvent:
    return WorldEvent(
        event_id=event_id,
        event_type=event_type,
        actor_ids=("project", "server-a"),
        occurred_at=occurred_at,
        source_id="runtime",
        summary=event_type + " 发生",
        confidence=0.9,
    )


def trial(*, counter: tuple[str, ...] = ()) -> CounterfactualTrial:
    return CounterfactualTrial(
        trial_id="t1",
        hypothesis_id="h1",
        expected_event_type="deploy_ok",
        counter_event_types=counter,
        created_at="2026-07-20T00:00:00+00:00",
        horizon_days=7,
    )


def test_supporting_event_confirms_trial() -> None:
    decided = decide_trial(
        trial(),
        (event("e1", "deploy_ok", "2026-07-21T10:00:00+00:00"),),
        now=NOW,
    )

    assert decided.status == TRIAL_STATUS_SUPPORTED
    assert decided.evidence_event_id == "e1"


def test_counter_event_wins_over_supporting_event() -> None:
    decided = decide_trial(
        trial(counter=("deploy_failed",)),
        (
            event("e1", "deploy_ok", "2026-07-21T10:00:00+00:00"),
            event("e2", "deploy_failed", "2026-07-21T11:00:00+00:00"),
        ),
        now=NOW,
    )

    assert decided.status == TRIAL_STATUS_REFUTED
    assert decided.evidence_event_id == "e2"


def test_trial_expires_after_horizon_without_evidence() -> None:
    after_deadline = dt.datetime(2026, 8, 5, 12, tzinfo=dt.UTC)
    decided = decide_trial(trial(), (), now=after_deadline)

    assert decided.status == TRIAL_STATUS_EXPIRED


def test_trial_stays_pending_inside_horizon() -> None:
    pending = CounterfactualTrial(
        trial_id="t1",
        hypothesis_id="h1",
        expected_event_type="deploy_ok",
        created_at="2026-07-21T00:00:00+00:00",
        horizon_days=7,
    )

    decided = decide_trial(pending, (), now=NOW)

    assert decided.status == "pending"
    assert decided == pending


def test_decided_trial_is_idempotent() -> None:
    supported = decide_trial(trial(), (event("e1", "deploy_ok", "2026-07-21T10:00:00+00:00"),), now=NOW)

    again = decide_trial(supported, (), now=NOW)

    assert again == supported


def test_resolution_confirms_strong_supported_and_removes_refuted() -> None:
    hypotheses = (
        CausalHypothesis("h1", "cause", "effect", "配置变化导致恢复", 0.9, (), False),
        CausalHypothesis("h2", "cause", "effect2", "配置变化导致失败", 0.9, (), False),
    )
    trials = (
        CounterfactualTrial("t1", "h1", "deploy_ok", created_at="2026-07-20T00:00:00+00:00", horizon_days=7),
        CounterfactualTrial("t2", "h2", "deploy_ok", counter_event_types=("deploy_failed",), created_at="2026-07-20T00:00:00+00:00", horizon_days=7),
    )
    events = (
        event("e1", "deploy_ok", "2026-07-21T10:00:00+00:00"),
        event("e2", "deploy_failed", "2026-07-21T11:00:00+00:00"),
    )

    resolution = resolve_counterfactual_trials(hypotheses, trials, events, now=NOW)

    assert resolution.refuted_hypothesis_ids == ("h2",)
    assert resolution.supported_hypothesis_ids == ("h1",)
    assert [item.hypothesis_id for item in resolution.hypotheses] == ["h1"]
    assert resolution.hypotheses[0].confirmed is True
    assert "counterfactual_support" in resolution.hypotheses[0].evidence_ids
    assert resolution == resolve_counterfactual_trials(hypotheses, trials, events, now=NOW)


def test_scenario_dataset_evaluates_all_pass() -> None:
    path = Path(__file__).resolve().parents[2] / "data" / "world_model_counterfactual_scenarios.json"
    document = json.loads(path.read_text(encoding="utf-8"))

    result = evaluate_scenarios(document, now=dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC))

    assert result["status"] == "PASS"
    assert result["failed"] == 0
    assert result["passed"] == len(document["scenarios"])
    assert result["margin"] == 1.0


def test_supported_low_confidence_stays_unconfirmed() -> None:
    hypotheses = (CausalHypothesis("h1", "cause", "effect", "弱证据假设", 0.6, (), False),)
    trials = (CounterfactualTrial("t1", "h1", "deploy_ok", created_at="2026-07-20T00:00:00+00:00", horizon_days=7),)
    events = (event("e1", "deploy_ok", "2026-07-21T10:00:00+00:00"),)

    resolution = resolve_counterfactual_trials(hypotheses, trials, events, now=NOW)

    assert resolution.hypotheses[0].confirmed is False
    assert "h1" in resolution.supported_hypothesis_ids
