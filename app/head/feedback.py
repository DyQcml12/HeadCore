from __future__ import annotations

import json

from app.head.contracts import FeedbackOutcome, HeadFeedback, HeadReflection


ACCEPT_MARKERS = ("这就对了", "对的", "可以", "明白了", "解决了", "好多了", "谢谢")
CORRECTION_MARKERS = ("不是这个意思", "你理解错了", "我说的是", "答非所问", "不对")
ADVICE_REJECTION_MARKERS = ("不想听大道理", "别讲道理", "别建议", "不用建议", "别说教")
CONTINUE_MARKERS = ("继续", "接着", "然后", "下一步")
STOP_MARKERS = ("算了", "不说了", "停下", "不用了", "到此为止")


def build_head_feedback(*, user_input: str, previous_action_json: str) -> HeadFeedback:
    previous = _load_previous_action(previous_action_json)
    previous_action = str(previous.get("action") or "none")
    if previous_action == "none":
        return HeadFeedback("none", FeedbackOutcome.UNKNOWN, ())

    text = user_input.strip()
    if signals := _matched_signals(text, CORRECTION_MARKERS):
        return HeadFeedback(
            previous_action,
            FeedbackOutcome.CORRECTED,
            signals,
            HeadReflection(
                mistake_type="misunderstood_user_intent",
                cause="previous_action_did_not_match_user_meaning",
                evidence=signals,
                better_action="acknowledge_correction_and_restate_understanding",
                policy_candidate="increase_clarification_when_meaning_is_ambiguous",
            ),
        )
    if signals := _matched_signals(text, ADVICE_REJECTION_MARKERS):
        return HeadFeedback(
            previous_action,
            FeedbackOutcome.ADVICE_REJECTED,
            signals,
            HeadReflection(
                mistake_type="premature_advice",
                cause="advice_was_not_requested_or_was_explicitly_rejected",
                evidence=signals,
                better_action="acknowledge_and_listen_without_advice",
                policy_candidate="set_advice_budget_to_zero_for_this_turn",
            ),
        )
    if signals := _matched_signals(text, ACCEPT_MARKERS):
        return HeadFeedback(previous_action, FeedbackOutcome.ACCEPTED, signals)
    if signals := _matched_signals(text, STOP_MARKERS):
        return HeadFeedback(previous_action, FeedbackOutcome.STOPPED, signals)
    if signals := _matched_signals(text, CONTINUE_MARKERS):
        return HeadFeedback(previous_action, FeedbackOutcome.CONTINUED, signals)
    return HeadFeedback(previous_action, FeedbackOutcome.UNKNOWN, ())


def encode_head_action(*, action: str, reason: str, advice_budget: int) -> str:
    return json.dumps(
        {"action": action, "reason": reason, "advice_budget": advice_budget},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def encode_head_feedback(feedback: HeadFeedback) -> str:
    payload: dict[str, object] = {
        "previous_action": feedback.previous_action,
        "outcome": feedback.outcome.value,
        "signals": list(feedback.signals),
    }
    if feedback.reflection is not None:
        payload["reflection"] = {
            "mistake_type": feedback.reflection.mistake_type,
            "cause": feedback.reflection.cause,
            "evidence": list(feedback.reflection.evidence),
            "better_action": feedback.reflection.better_action,
            "policy_candidate": feedback.reflection.policy_candidate,
        }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _load_previous_action(value: str) -> dict[str, object]:
    if not value or value == "none":
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _matched_signals(text: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(marker for marker in markers if marker in text)
