from __future__ import annotations

import json
from dataclasses import asdict, replace

from app.head.contracts import (
    HeadLongTermPlan,
    HeadExecutionEvidence,
    HeadPlanStep,
    LongTermPlanStatus,
    PlanStepStatus,
    ExecutionEvidenceSource,
)
from app.head.long_term_planning import build_long_term_plan, validate_execution_evidence
from app.storage.chat_repository import ChatRepository


LONG_TERM_PLAN_MEMORY_TYPE = "head_long_term_plan"
LONG_TERM_PLAN_SCHEMA_VERSION = 1


def encode_long_term_plan(plan: HeadLongTermPlan) -> str:
    _validate_runtime_state(plan)
    return json.dumps(
        {"schema_version": LONG_TERM_PLAN_SCHEMA_VERSION, "plan": asdict(plan)},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_long_term_plan(content: str) -> HeadLongTermPlan:
    try:
        payload = json.loads(content)
        if payload.get("schema_version") != LONG_TERM_PLAN_SCHEMA_VERSION:
            raise ValueError("unsupported long-term plan schema")
        raw = payload["plan"]
        steps = tuple(
            HeadPlanStep(
                step_id=item["step_id"],
                objective=item["objective"],
                depends_on=tuple(item.get("depends_on", [])),
                completion_criteria=item["completion_criteria"],
                status=PlanStepStatus(item.get("status", "pending")),
                attempts=int(item.get("attempts", 0)),
                max_attempts=int(item.get("max_attempts", 2)),
                evidence=tuple(
                    HeadExecutionEvidence(
                        evidence_id=value["evidence_id"],
                        source=ExecutionEvidenceSource(value["source"]),
                        reference=value["reference"],
                        observed_at=value["observed_at"],
                        succeeded=bool(value["succeeded"]),
                        expires_at=value.get("expires_at"),
                    )
                    for value in item.get("evidence", [])
                ),
                failure_reason=item.get("failure_reason"),
            )
            for item in raw["steps"]
        )
        validated = build_long_term_plan(raw["plan_id"], raw["goal"], steps)
        plan = replace(
            validated,
            status=LongTermPlanStatus(raw.get("status", "pending")),
            version=int(raw.get("version", 1)),
            replan_count=int(raw.get("replan_count", 0)),
            max_replans=int(raw.get("max_replans", 2)),
            current_step_id=raw.get("current_step_id"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid persisted long-term plan") from exc
    _validate_runtime_state(plan)
    return plan


async def save_long_term_plan(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str | None,
    plan: HeadLongTermPlan,
    allow_write: bool,
) -> None:
    if not allow_write:
        return
    await repository.save_memory(
        user_id=user_id,
        session_id=session_id,
        memory_type=LONG_TERM_PLAN_MEMORY_TYPE,
        content=encode_long_term_plan(plan),
        source_message_id=source_message_id,
        confidence=1.0,
    )


async def load_long_term_plan(
    repository: ChatRepository,
    *,
    user_id: str,
) -> HeadLongTermPlan | None:
    records = await repository.list_memories(
        user_id=user_id,
        memory_types=[LONG_TERM_PLAN_MEMORY_TYPE],
        limit=4,
    )
    for record in reversed(records):
        try:
            return decode_long_term_plan(record.content)
        except ValueError:
            continue
    return None


def _validate_runtime_state(plan: HeadLongTermPlan) -> None:
    if plan.version < 1 or plan.replan_count < 0 or not 0 <= plan.replan_count <= plan.max_replans:
        raise ValueError("invalid long-term plan version or replan budget")
    active = [step.step_id for step in plan.steps if step.status == PlanStepStatus.ACTIVE]
    if len(active) > 1 or (plan.current_step_id is not None and active != [plan.current_step_id]):
        raise ValueError("long-term plan current step is inconsistent")
    for step in plan.steps:
        if not 0 <= step.attempts <= step.max_attempts:
            raise ValueError("long-term plan step attempts are invalid")
        if step.status == PlanStepStatus.COMPLETED and not step.evidence:
            raise ValueError("completed long-term plan step requires evidence")
        if step.status == PlanStepStatus.COMPLETED:
            validate_execution_evidence(step.evidence, enforce_freshness=False)
