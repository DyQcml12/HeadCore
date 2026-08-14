from __future__ import annotations

import datetime as dt
import json
from dataclasses import replace

from app.head.contracts import (
    CommunicationState,
    FeedbackOutcome,
    HeadAdaptivePolicy,
    HeadEventRecord,
    HeadFeedback,
)


POLICY_TTL = dt.timedelta(days=7)
ACTIVATION_THRESHOLD = 2
RESET_MARKERS = (
    "恢复默认沟通策略",
    "恢复默认回复策略",
    "取消短期策略",
    "清除短期沟通偏好",
)


def build_adaptive_policy(
    *,
    feedback_events: tuple[HeadEventRecord, ...],
    current_feedback: HeadFeedback,
    policy_reset_at: str | None,
    user_input: str,
    now: dt.datetime | None = None,
) -> HeadAdaptivePolicy:
    current_time = now or dt.datetime.now(dt.UTC)
    if is_policy_reset_request(user_input):
        return HeadAdaptivePolicy()
    reset_at = _parse_time(policy_reset_at)
    outcomes: list[tuple[FeedbackOutcome, dt.datetime]] = []
    for event in feedback_events:
        created_at = _parse_time(event.created_at)
        if created_at is None or current_time - created_at > POLICY_TTL:
            continue
        if reset_at is not None and created_at <= reset_at:
            continue
        outcome = _decode_outcome(event.content)
        if outcome is not None:
            outcomes.append((outcome, created_at))
    if current_feedback.outcome != FeedbackOutcome.UNKNOWN:
        outcomes.append((current_feedback.outcome, current_time))

    counts = {outcome: sum(1 for value, _ in outcomes if value == outcome) for outcome in FeedbackOutcome}
    reasons: list[str] = []
    advice_cap = None
    clarification_bias = False
    persona_cap = None
    if counts[FeedbackOutcome.ADVICE_REJECTED] >= ACTIVATION_THRESHOLD:
        advice_cap = 0
        persona_cap = 0.2
        reasons.append("repeated_advice_rejection")
    if counts[FeedbackOutcome.CORRECTED] >= ACTIVATION_THRESHOLD:
        clarification_bias = True
        persona_cap = min(persona_cap or 1.0, 0.25)
        reasons.append("repeated_intent_correction")
    if not reasons:
        return HeadAdaptivePolicy()
    evidence_count = sum(counts[outcome] for outcome in (FeedbackOutcome.ADVICE_REJECTED, FeedbackOutcome.CORRECTED))
    newest = max(created_at for _, created_at in outcomes)
    return HeadAdaptivePolicy(
        active=True,
        version=evidence_count,
        evidence_count=evidence_count,
        advice_budget_cap=advice_cap,
        clarification_bias=clarification_bias,
        persona_intensity_cap=persona_cap,
        reasons=tuple(reasons),
        expires_at=(newest + POLICY_TTL).isoformat(timespec="seconds"),
    )


def apply_adaptive_policy(
    communication: CommunicationState,
    policy: HeadAdaptivePolicy,
) -> CommunicationState:
    if not policy.active:
        return communication
    turn = communication.turn_policy
    advice_budget = turn.advice_budget
    persona_intensity = turn.persona_intensity
    constraints = list(turn.constraints)
    if policy.advice_budget_cap is not None:
        advice_budget = min(advice_budget, policy.advice_budget_cap)
        constraints.append("adaptive_no_unsolicited_advice")
    if policy.clarification_bias:
        constraints.append("adaptive_clarify_when_ambiguous")
    if policy.persona_intensity_cap is not None:
        persona_intensity = min(persona_intensity, policy.persona_intensity_cap)
    return replace(
        communication,
        turn_policy=replace(
            turn,
            advice_budget=advice_budget,
            persona_intensity=persona_intensity,
            constraints=tuple(dict.fromkeys(constraints)),
        ),
    )


def is_policy_reset_request(user_input: str) -> bool:
    return any(marker in user_input for marker in RESET_MARKERS)


def _decode_outcome(content: str) -> FeedbackOutcome | None:
    try:
        payload = json.loads(content)
        return FeedbackOutcome(str(payload.get("outcome")))
    except (AttributeError, TypeError, ValueError):
        return None


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.UTC)
