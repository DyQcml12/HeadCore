from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import Iterable

from app.head.contracts import CausalHypothesis, WorldEvent
from app.head.world_model import _parse_time


TRIAL_STATUS_PENDING = "pending"
TRIAL_STATUS_SUPPORTED = "supported"
TRIAL_STATUS_REFUTED = "refuted"
TRIAL_STATUS_EXPIRED = "expired"


@dataclass(frozen=True)
class CounterfactualTrial:
    trial_id: str
    hypothesis_id: str
    expected_event_type: str
    counter_event_types: tuple[str, ...] = ()
    created_at: str = ""
    horizon_days: int = 7
    status: str = TRIAL_STATUS_PENDING
    evidence_event_id: str | None = None
    decided_at: str | None = None

    def __post_init__(self) -> None:
        if not self.trial_id.strip():
            raise ValueError("counterfactual trial_id is required")
        if not self.hypothesis_id.strip():
            raise ValueError("counterfactual hypothesis_id is required")
        if not self.expected_event_type.strip():
            raise ValueError("counterfactual expected_event_type is required")
        if self.horizon_days < 1:
            raise ValueError("counterfactual horizon_days must be positive")


@dataclass(frozen=True)
class CounterfactualResolution:
    hypotheses: tuple[CausalHypothesis, ...]
    trials: tuple[CounterfactualTrial, ...]
    refuted_hypothesis_ids: tuple[str, ...]
    supported_hypothesis_ids: tuple[str, ...]


def decide_trial(
    trial: CounterfactualTrial,
    events: Iterable[WorldEvent],
    *,
    now: dt.datetime | None = None,
) -> CounterfactualTrial:
    """Advance one trial through pending -> supported/refuted/expired.

    Deterministic for a fixed now. A decided trial is returned unchanged.
    Counter evidence (any event whose type matches counter_event_types inside
    the horizon) always wins over supporting evidence."""
    if trial.status != TRIAL_STATUS_PENDING:
        return trial
    current_time = _parse_aware(now or dt.datetime.now(dt.UTC))
    created = _parse_time(trial.created_at) if trial.created_at else current_time
    deadline = created + dt.timedelta(days=trial.horizon_days)
    event_items = sorted(events, key=lambda item: _parse_time(item.occurred_at))
    for event in event_items:
        occurred = _parse_time(event.occurred_at)
        if occurred < created or occurred > deadline:
            continue
        if event.event_type in trial.counter_event_types:
            return replace(
                trial,
                status=TRIAL_STATUS_REFUTED,
                evidence_event_id=event.event_id,
                decided_at=current_time.isoformat(),
            )
    for event in event_items:
        occurred = _parse_time(event.occurred_at)
        if occurred < created or occurred > deadline:
            continue
        if event.event_type == trial.expected_event_type:
            return replace(
                trial,
                status=TRIAL_STATUS_SUPPORTED,
                evidence_event_id=event.event_id,
                decided_at=current_time.isoformat(),
            )
    if current_time > deadline:
        return replace(
            trial,
            status=TRIAL_STATUS_EXPIRED,
            decided_at=current_time.isoformat(),
        )
    return trial


def resolve_counterfactual_trials(
    hypotheses: Iterable[CausalHypothesis],
    trials: Iterable[CounterfactualTrial],
    events: Iterable[WorldEvent],
    *,
    now: dt.datetime | None = None,
) -> CounterfactualResolution:
    """Apply trial outcomes to causal hypotheses.

    supported -> confirmed only when the hypothesis already has confidence >= 0.8
    (confirmed hypotheses require evidence and strong confidence by contract);
    refuted -> the hypothesis is removed from the projectable set and reported;
    expired/pending hypotheses stay unconfirmed with their existing evidence.
    """
    event_items = tuple(events)
    decided_trials = tuple(decide_trial(trial, event_items, now=now) for trial in trials)
    refuted_ids = {
        trial.hypothesis_id
        for trial in decided_trials
        if trial.status == TRIAL_STATUS_REFUTED
    }
    supported_ids = {
        trial.hypothesis_id
        for trial in decided_trials
        if trial.status == TRIAL_STATUS_SUPPORTED
    }
    kept: list[CausalHypothesis] = []
    for hypothesis in hypotheses:
        if hypothesis.hypothesis_id in refuted_ids:
            continue
        if hypothesis.hypothesis_id in supported_ids and hypothesis.confidence >= 0.8:
            kept.append(
                replace(
                    hypothesis,
                    confirmed=True,
                    evidence_ids=tuple(dict.fromkeys((*hypothesis.evidence_ids, "counterfactual_support"))),
                )
            )
        else:
            kept.append(hypothesis)
    return CounterfactualResolution(
        hypotheses=tuple(kept),
        trials=decided_trials,
        refuted_hypothesis_ids=tuple(sorted(refuted_ids)),
        supported_hypothesis_ids=tuple(sorted(supported_ids)),
    )


def _parse_aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise ValueError("counterfactual timestamps must include a timezone")
    return value.astimezone(dt.UTC)
