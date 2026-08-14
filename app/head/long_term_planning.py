from __future__ import annotations

import re
import datetime as dt
from dataclasses import replace

from app.head.contracts import (
    HeadLongTermPlan,
    HeadExecutionEvidence,
    HeadPlanStep,
    HeadWorldModel,
    LongTermPlanStatus,
    PlanStepStatus,
    ExecutionEvidenceSource,
)

WORLD_EVENT_EVIDENCE_MAX_AGE = dt.timedelta(days=30)
WORLD_EVENT_EVIDENCE_MIN_CONFIDENCE = 0.8


def build_long_term_plan(plan_id: str, goal: str, steps: tuple[HeadPlanStep, ...]) -> HeadLongTermPlan:
    _validate_text(goal, "goal", 240)
    _validate_id(plan_id, "plan_id")
    if not 1 <= len(steps) <= 16:
        raise ValueError("long-term plan requires 1 to 16 steps")
    step_ids = {step.step_id for step in steps}
    if len(step_ids) != len(steps):
        raise ValueError("duplicate long-term plan step_id")
    for step in steps:
        _validate_id(step.step_id, "step_id")
        _validate_text(step.objective, "step objective", 240)
        _validate_text(step.completion_criteria, "completion criteria", 240)
        if set(step.depends_on) - step_ids:
            raise ValueError(f"step {step.step_id} has unknown dependency")
        if step.step_id in step.depends_on:
            raise ValueError(f"step {step.step_id} cannot depend on itself")
        if not 1 <= step.max_attempts <= 5:
            raise ValueError("step max_attempts must be between 1 and 5")
    _reject_dependency_cycles(steps)
    return HeadLongTermPlan(plan_id=plan_id, goal=goal, steps=steps)


def activate_next_step(plan: HeadLongTermPlan) -> HeadLongTermPlan:
    if plan.status in {LongTermPlanStatus.COMPLETED, LongTermPlanStatus.FAILED}:
        return plan
    completed = {step.step_id for step in plan.steps if step.status == PlanStepStatus.COMPLETED}
    if len(completed) == len(plan.steps):
        return replace(plan, status=LongTermPlanStatus.COMPLETED, current_step_id=None)
    if any(step.status == PlanStepStatus.ACTIVE for step in plan.steps):
        return plan
    eligible = next(
        (
            step
            for step in plan.steps
            if step.status == PlanStepStatus.PENDING and set(step.depends_on) <= completed
        ),
        None,
    )
    if eligible is None:
        return replace(plan, status=LongTermPlanStatus.BLOCKED, current_step_id=None)
    steps = tuple(
        replace(step, status=PlanStepStatus.ACTIVE) if step.step_id == eligible.step_id else step
        for step in plan.steps
    )
    return replace(
        plan,
        steps=steps,
        status=LongTermPlanStatus.ACTIVE,
        current_step_id=eligible.step_id,
    )


def record_step_result(
    plan: HeadLongTermPlan,
    *,
    step_id: str,
    succeeded: bool,
    evidence: tuple[HeadExecutionEvidence, ...] = (),
    failure_reason: str | None = None,
    now: dt.datetime | None = None,
) -> HeadLongTermPlan:
    step = _step(plan, step_id)
    if step.status != PlanStepStatus.ACTIVE or plan.current_step_id != step_id:
        raise ValueError("only the active long-term plan step can record a result")
    if succeeded:
        validate_execution_evidence(evidence, now=now)
    if not succeeded and not (failure_reason or "").strip():
        raise ValueError("failed plan step requires a reason")
    attempts = step.attempts + 1
    if succeeded:
        updated = replace(
            step,
            status=PlanStepStatus.COMPLETED,
            attempts=attempts,
            evidence=evidence,
            failure_reason=None,
        )
    elif attempts < step.max_attempts:
        updated = replace(
            step,
            status=PlanStepStatus.PENDING,
            attempts=attempts,
            failure_reason=failure_reason,
        )
    else:
        updated = replace(
            step,
            status=PlanStepStatus.FAILED,
            attempts=attempts,
            failure_reason=failure_reason,
        )
    steps = tuple(updated if item.step_id == step_id else item for item in plan.steps)
    failed = updated.status == PlanStepStatus.FAILED
    next_plan = replace(
        plan,
        steps=steps,
        status=LongTermPlanStatus.BLOCKED if failed else LongTermPlanStatus.ACTIVE,
        current_step_id=None,
    )
    return activate_next_step(next_plan) if not failed else next_plan


def record_step_result_from_world_events(
    plan: HeadLongTermPlan,
    *,
    step_id: str,
    world_model: HeadWorldModel,
    event_ids: tuple[str, ...],
    now: dt.datetime | None = None,
) -> HeadLongTermPlan:
    """Complete an active step only from explicitly selected fresh world events."""
    evidence = build_world_event_evidence(world_model, event_ids=event_ids, now=now)
    return record_step_result(plan, step_id=step_id, succeeded=True, evidence=evidence, now=now)


def build_world_event_evidence(
    world_model: HeadWorldModel,
    *,
    event_ids: tuple[str, ...],
    now: dt.datetime | None = None,
) -> tuple[HeadExecutionEvidence, ...]:
    if not event_ids:
        raise ValueError("world event completion requires event_ids")
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("world event completion event_ids must be unique")
    current_time = _aware(now or dt.datetime.now(dt.UTC))
    events = {event.event_id: event for event in world_model.events}
    evidence: list[HeadExecutionEvidence] = []
    for event_id in event_ids:
        event = events.get(event_id)
        if event is None:
            raise ValueError(f"world event completion references unknown event: {event_id}")
        occurred_at = _parse_time(event.occurred_at)
        if occurred_at > current_time + dt.timedelta(minutes=5):
            raise ValueError("world event completion cannot use a future event")
        if occurred_at < current_time - WORLD_EVENT_EVIDENCE_MAX_AGE:
            raise ValueError("world event completion cannot use a stale event")
        if event.confidence < WORLD_EVENT_EVIDENCE_MIN_CONFIDENCE:
            raise ValueError("world event completion requires confidence >= 0.8")
        evidence.append(
            HeadExecutionEvidence(
                evidence_id=f"world_event:{event.event_id}",
                source=ExecutionEvidenceSource.WORLD_EVENT,
                reference=f"world_event:{event.event_id};source={event.source_id}",
                observed_at=event.occurred_at,
                succeeded=True,
            )
        )
    return tuple(evidence)


def validate_execution_evidence(
    evidence: tuple[HeadExecutionEvidence, ...],
    *,
    now: dt.datetime | None = None,
    enforce_freshness: bool = True,
) -> None:
    if not evidence:
        raise ValueError("successful plan step requires completion evidence")
    current_time = _aware(now or dt.datetime.now(dt.UTC))
    ids: set[str] = set()
    for item in evidence:
        _validate_id(item.evidence_id, "evidence_id")
        _validate_text(item.reference, "evidence reference", 240)
        if item.evidence_id in ids:
            raise ValueError("duplicate execution evidence_id")
        ids.add(item.evidence_id)
        if item.source == ExecutionEvidenceSource.MODEL_CLAIM:
            raise ValueError("model claims cannot complete a plan step")
        if not item.succeeded:
            raise ValueError("failed execution evidence cannot complete a plan step")
        observed_at = _parse_time(item.observed_at)
        if enforce_freshness and observed_at > current_time + dt.timedelta(minutes=5):
            raise ValueError("execution evidence cannot be from the future")
        if (
            enforce_freshness
            and item.expires_at is not None
            and _parse_time(item.expires_at) <= current_time
        ):
            raise ValueError("expired execution evidence cannot complete a plan step")


def replan_remaining_steps(
    plan: HeadLongTermPlan,
    *,
    replacement_steps: tuple[HeadPlanStep, ...],
) -> HeadLongTermPlan:
    if plan.status != LongTermPlanStatus.BLOCKED:
        raise ValueError("only a blocked long-term plan can be replanned")
    if plan.replan_count >= plan.max_replans:
        return replace(plan, status=LongTermPlanStatus.FAILED, current_step_id=None)
    completed = tuple(step for step in plan.steps if step.status == PlanStepStatus.COMPLETED)
    rebuilt = build_long_term_plan(plan.plan_id, plan.goal, completed + replacement_steps)
    return activate_next_step(
        replace(
            rebuilt,
            version=plan.version + 1,
            replan_count=plan.replan_count + 1,
            max_replans=plan.max_replans,
        )
    )


def current_plan_step(plan: HeadLongTermPlan) -> HeadPlanStep | None:
    return _step(plan, plan.current_step_id) if plan.current_step_id else None


def project_long_term_plan(plan: HeadLongTermPlan) -> tuple[str, ...]:
    current = current_plan_step(plan)
    values = [
        f"长期目标={plan.goal};status={plan.status.value};version={plan.version};"
        f"replans={plan.replan_count}/{plan.max_replans}"
    ]
    if current:
        values.append(
            f"当前计划步骤={current.step_id}:{current.objective};"
            f"完成条件={current.completion_criteria};attempts={current.attempts}/{current.max_attempts}"
        )
    return tuple(values)


def _step(plan: HeadLongTermPlan, step_id: str | None) -> HeadPlanStep:
    for step in plan.steps:
        if step.step_id == step_id:
            return step
    raise ValueError(f"unknown long-term plan step: {step_id}")


def _reject_dependency_cycles(steps: tuple[HeadPlanStep, ...]) -> None:
    dependencies = {step.step_id: set(step.depends_on) for step in steps}
    remaining = set(dependencies)
    while remaining:
        ready = {step_id for step_id in remaining if not (dependencies[step_id] & remaining)}
        if not ready:
            raise ValueError("long-term plan dependencies contain a cycle")
        remaining -= ready


def _validate_id(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,95}", value):
        raise ValueError(f"invalid long-term plan {label}")


def _validate_text(value: str, label: str, limit: int) -> None:
    if not value.strip() or len(value) > limit or any(char in value for char in "\r\n\x00"):
        raise ValueError(f"long-term plan {label} must be one bounded line")


def _parse_time(value: str) -> dt.datetime:
    try:
        return _aware(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError("execution evidence timestamp must be ISO-8601") from exc


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise ValueError("execution evidence timestamps must include a timezone")
    return value.astimezone(dt.UTC)
