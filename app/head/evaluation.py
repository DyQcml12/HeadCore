from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from app.head.contracts import HeadAction, HeadEventContext
from app.head.state import build_head_state
from app.mind.conversation_state import build_conversation_state
from app.mind.self_state import build_self_state
from app.mind.social_state import build_social_state
from app.persona.relationship_context import DEFAULT_RELATIONSHIP_CONTEXT


def load_planning_scenarios(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("planning scenario file must contain a JSON list")
    required = {"id", "user_input", "expected_action", "expected_complex"}
    for index, scenario in enumerate(payload):
        if not isinstance(scenario, dict) or not required.issubset(scenario):
            raise ValueError(f"invalid planning scenario at index {index}")
    return payload


def evaluate_planning_scenarios(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    results = [evaluate_planning_scenario(scenario) for scenario in scenarios]
    passed = sum(1 for result in results if result["passed"])
    selected_correct = sum(1 for result in results if result["selected_action_correct"])
    complex_correct = sum(1 for result in results if result["complexity_correct"])
    return {
        "status": "PASS" if passed == len(results) else "FAIL",
        "scenario_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "selection_accuracy": _ratio(selected_correct, len(results)),
        "complexity_accuracy": _ratio(complex_correct, len(results)),
        "average_selected_risk": round(
            sum(float(result["selected_risk"]) for result in results) / max(len(results), 1), 4
        ),
        "results": results,
    }


def evaluate_planning_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    state = _build_scenario_state(scenario)
    plan = state.plan
    selected = plan.candidates[plan.selected_index]
    expected_action = HeadAction(str(scenario["expected_action"]))
    expected_candidates = [item for item in plan.candidates if item.action == expected_action]
    best_expected_score = max((item.score.total for item in expected_candidates), default=None)
    runner_up = max(
        (item.score.total for index, item in enumerate(plan.candidates) if index != plan.selected_index),
        default=selected.score.total,
    )
    selected_risk = max(
        selected.score.boundary_risk,
        selected.score.moralizing_risk,
        selected.score.fabrication_risk,
    )
    reasons: list[str] = []
    selected_action_correct = selected.action == expected_action
    complexity_correct = plan.complex_scene is bool(scenario["expected_complex"])
    if not selected_action_correct:
        reasons.append("wrong_selected_action")
    if not complexity_correct:
        reasons.append("wrong_complexity_classification")
    if len(plan.candidates) > int(scenario.get("max_candidates", 4)):
        reasons.append("candidate_budget_exceeded")
    forbidden = {HeadAction(value) for value in scenario.get("forbidden_candidate_actions", [])}
    if any(item.action in forbidden for item in plan.candidates):
        reasons.append("forbidden_candidate_present")
    max_risk = float(scenario.get("max_selected_risk", 1.0))
    if selected_risk > max_risk:
        reasons.append("selected_risk_exceeded")
    if best_expected_score is None:
        reasons.append("expected_candidate_missing")
    return {
        "id": str(scenario["id"]),
        "title": str(scenario.get("title") or ""),
        "passed": not reasons,
        "reasons": reasons,
        "expected_action": expected_action.value,
        "selected_action": selected.action.value,
        "selected_action_correct": selected_action_correct,
        "expected_complex": bool(scenario["expected_complex"]),
        "actual_complex": plan.complex_scene,
        "complexity_correct": complexity_correct,
        "candidate_count": len(plan.candidates),
        "selected_score": selected.score.total,
        "selected_risk": round(selected_risk, 4),
        "selection_margin": round(selected.score.total - runner_up, 4),
        "expected_action_best_score": best_expected_score,
        "counterfactual_score_gap": (
            round(selected.score.total - best_expected_score, 4)
            if best_expected_score is not None
            else None
        ),
        "candidates": [
            {
                "action": item.action.value,
                "reason": item.reason,
                "objective": item.objective,
                "score": asdict(item.score),
            }
            for item in plan.candidates
        ],
    }


def _build_scenario_state(scenario: dict[str, Any]):  # type: ignore[no-untyped-def]
    user_input = str(scenario["user_input"])
    relationship_role = str(scenario.get("relationship_role") or "normal_friend")
    relationship = replace(DEFAULT_RELATIONSHIP_CONTEXT, role=relationship_role)
    conversation = build_conversation_state(user_input=user_input, recent_messages=[])
    social = build_social_state(
        relationship=relationship,
        conversation=conversation,
        recent_messages=[],
        user_input=user_input,
    )
    event_context = HeadEventContext(
        active_task=str(scenario.get("active_task") or "none"),
        last_action=str(scenario.get("last_action") or "none"),
    )
    return build_head_state(
        subject_id="planning-eval-user",
        user_input=user_input,
        relationship_role=relationship_role,
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=social,
        recent_messages=[],
        event_context=event_context,
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
