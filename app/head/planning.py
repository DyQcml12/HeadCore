from __future__ import annotations

from app.head.contracts import (
    CommunicationAct,
    CommunicationState,
    HeadAction,
    HeadActionScore,
    HeadCandidateAction,
    HeadDecision,
    HeadFeedback,
    HeadPlan,
)


def build_head_plan(
    *,
    base_decision: HeadDecision,
    user_input: str,
    current_topic: str,
    relationship_role: str,
    active_task: str,
    uncertainties: tuple[str, ...],
    communication: CommunicationState,
    feedback: HeadFeedback,
) -> HeadPlan:
    complex_scene = _is_complex_scene(
        user_input=user_input,
        current_topic=current_topic,
        relationship_role=relationship_role,
        active_task=active_task,
        uncertainties=uncertainties,
        communication=communication,
        feedback=feedback,
    )
    base = _candidate(
        action=base_decision.action,
        reason=base_decision.reason,
        objective=base_decision.objective,
        current_topic=current_topic,
        active_task=active_task,
        uncertainties=uncertainties,
        communication=communication,
        is_base=True,
    )
    if base_decision.reason.startswith("world_"):
        return HeadPlan(False, (base,), 0, "single_action_world_evidence")
    if not complex_scene or relationship_role == "blocked":
        return HeadPlan(False, (base,), 0, "single_action_low_latency")

    candidates = [base]
    if base_decision.action != HeadAction.CLARIFY and (
        uncertainties or communication.turn_policy.question_budget > 0
    ):
        candidates.append(
            _candidate(
                action=HeadAction.CLARIFY,
                reason="candidate_clarify",
                objective="先确认关键歧义，再继续回答",
                current_topic=current_topic,
                active_task=active_task,
                uncertainties=uncertainties,
                communication=communication,
            )
        )
    if base_decision.action != HeadAction.CONTINUE_TASK and active_task != "none":
        candidates.append(
            _candidate(
                action=HeadAction.CONTINUE_TASK,
                reason="candidate_progress_task",
                objective="利用已知信息推进一个可验证步骤",
                current_topic=current_topic,
                active_task=active_task,
                uncertainties=uncertainties,
                communication=communication,
            )
        )
    if (
        base_decision.action != HeadAction.SUPPORT
        and CommunicationAct.EMOTIONAL_SUPPORT in _all_acts(communication)
    ):
        candidates.append(
            _candidate(
                action=HeadAction.SUPPORT,
                reason="candidate_listen_first",
                objective="先确认感受并留出表达空间",
                current_topic=current_topic,
                active_task=active_task,
                uncertainties=uncertainties,
                communication=communication,
            )
        )
    if communication.turn_policy.advice_budget > 0 and len(candidates) < 4:
        candidates.append(
            _candidate(
                action=HeadAction.ANSWER,
                reason="candidate_direct_advice",
                objective="直接给出有限、可执行的建议",
                current_topic=current_topic,
                active_task=active_task,
                uncertainties=uncertainties,
                communication=communication,
            )
        )

    candidates = _deduplicate(candidates)[:4]
    selected_index = max(range(len(candidates)), key=lambda index: candidates[index].score.total)
    return HeadPlan(
        complex_scene=True,
        candidates=tuple(candidates),
        selected_index=selected_index,
        rationale="highest_multi_objective_score_with_risk_penalties",
    )


def selected_decision(plan: HeadPlan) -> HeadDecision:
    selected = plan.candidates[plan.selected_index]
    return HeadDecision(selected.action, selected.reason, selected.objective)


def _is_complex_scene(
    *,
    user_input: str,
    current_topic: str,
    relationship_role: str,
    active_task: str,
    uncertainties: tuple[str, ...],
    communication: CommunicationState,
    feedback: HeadFeedback,
) -> bool:
    if relationship_role == "blocked":
        return False
    acts = _all_acts(communication)
    return bool(
        uncertainties
        or feedback.reflection is not None
        or CommunicationAct.ACCEPT_CORRECTION in acts
        or current_topic == "technical_or_project" and (active_task != "none" or len(user_input) >= 20)
        or CommunicationAct.EMOTIONAL_SUPPORT in acts and len(user_input) >= 12
    )


def _candidate(
    *,
    action: HeadAction,
    reason: str,
    objective: str,
    current_topic: str,
    active_task: str,
    uncertainties: tuple[str, ...],
    communication: CommunicationState,
    is_base: bool = False,
) -> HeadCandidateAction:
    acts = _all_acts(communication)
    emotional = CommunicationAct.EMOTIONAL_SUPPORT in acts
    correction = CommunicationAct.ACCEPT_CORRECTION in acts
    avoid_advice = CommunicationAct.AVOID_ADVICE in acts or communication.turn_policy.advice_budget == 0
    intent_fit = 0.78 + (0.12 if is_base else 0.0)
    task_progress = 0.95 if action == HeadAction.CONTINUE_TASK and active_task != "none" else 0.55
    relationship_fit = 0.95 if action in {HeadAction.SUPPORT, HeadAction.REPAIR} and emotional else 0.8
    fact_reliability = 1.0 if action == HeadAction.CLARIFY and uncertainties else 0.78
    persona_consistency = 0.9 if action != HeadAction.REFUSE else 0.8
    boundary_risk = 0.0
    moralizing_risk = 0.85 if action == HeadAction.ANSWER and avoid_advice and emotional else 0.05
    fabrication_risk = 0.6 if action != HeadAction.CLARIFY and uncertainties else 0.02
    if action == HeadAction.CLARIFY and not uncertainties:
        intent_fit -= 0.2
        task_progress -= 0.2
    if action == HeadAction.SUPPORT and emotional:
        intent_fit += 0.12
        relationship_fit = 1.0
    if action == HeadAction.CONTINUE_TASK and current_topic == "technical_or_project":
        intent_fit += 0.1
    if emotional and action == HeadAction.CONTINUE_TASK:
        intent_fit -= 0.12
        relationship_fit -= 0.1
    if correction:
        if action == HeadAction.REPAIR:
            intent_fit += 0.15
            relationship_fit = 1.0
            task_progress = max(task_progress, 0.75)
        else:
            intent_fit -= 0.25
    total = (
        0.27 * intent_fit
        + 0.2 * task_progress
        + 0.14 * relationship_fit
        + 0.2 * fact_reliability
        + 0.09 * persona_consistency
        - 0.25 * boundary_risk
        - 0.18 * moralizing_risk
        - 0.22 * fabrication_risk
    )
    return HeadCandidateAction(
        action=action,
        reason=reason,
        objective=objective,
        score=HeadActionScore(
            intent_fit=round(intent_fit, 3),
            task_progress=round(task_progress, 3),
            relationship_fit=round(relationship_fit, 3),
            fact_reliability=round(fact_reliability, 3),
            persona_consistency=round(persona_consistency, 3),
            boundary_risk=round(boundary_risk, 3),
            moralizing_risk=round(moralizing_risk, 3),
            fabrication_risk=round(fabrication_risk, 3),
            total=round(total, 4),
        ),
    )


def _all_acts(communication: CommunicationState) -> tuple[CommunicationAct, ...]:
    return (communication.primary_act, *communication.secondary_acts)


def _deduplicate(candidates: list[HeadCandidateAction]) -> list[HeadCandidateAction]:
    unique: dict[tuple[HeadAction, str], HeadCandidateAction] = {}
    for candidate in candidates:
        unique[(candidate.action, candidate.objective)] = candidate
    return list(unique.values())
