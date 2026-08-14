from __future__ import annotations

import asyncio
import datetime as dt
import pytest

from app.head.contracts import (
    ExecutionEvidenceSource,
    HeadExecutionEvidence,
    HeadPlanStep,
    LongTermPlanStatus,
    PlanStepStatus,
)
from app.head.long_term_planning import (
    activate_next_step,
    build_world_event_evidence,
    build_long_term_plan,
    current_plan_step,
    project_long_term_plan,
    record_step_result,
    record_step_result_from_world_events,
    replan_remaining_steps,
)
from app.head.contracts import HeadWorldModel, WorldEntity, WorldEvent
from app.head.long_term_plan_store import load_long_term_plan, save_long_term_plan
from app.head.events import load_head_event_context
from app.storage.chat_repository import JsonlChatRepository


NOW = dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC)


def evidence(
    evidence_id: str = "ev1",
    *,
    source: ExecutionEvidenceSource = ExecutionEvidenceSource.TEST_RUNNER,
    succeeded: bool = True,
    observed_at: dt.datetime = NOW,
    expires_at: dt.datetime | None = None,
) -> HeadExecutionEvidence:
    return HeadExecutionEvidence(
        evidence_id=evidence_id,
        source=source,
        reference="tests/result.json",
        observed_at=observed_at.isoformat(),
        succeeded=succeeded,
        expires_at=expires_at.isoformat() if expires_at else None,
    )


def steps() -> tuple[HeadPlanStep, ...]:
    return (
        HeadPlanStep("inspect", "检查现有实现", completion_criteria="形成检查结果"),
        HeadPlanStep(
            "implement",
            "实现修改",
            depends_on=("inspect",),
            completion_criteria="代码通过专项测试",
        ),
        HeadPlanStep(
            "verify",
            "执行全量验证",
            depends_on=("implement",),
            completion_criteria="全量测试通过",
        ),
    )


def test_plan_advances_only_after_evidenced_completion() -> None:
    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", steps()))
    assert current_plan_step(plan).step_id == "inspect"  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="requires completion evidence"):
        record_step_result(plan, step_id="inspect", succeeded=True)

    plan = record_step_result(
        plan, step_id="inspect", succeeded=True, evidence=(evidence(),), now=NOW
    )
    assert current_plan_step(plan).step_id == "implement"  # type: ignore[union-attr]
    assert plan.steps[0].status == PlanStepStatus.COMPLETED


def test_dependency_cycle_and_skipped_step_are_rejected() -> None:
    cyclic = (
        HeadPlanStep("a", "步骤 A", ("b",), "A 完成"),
        HeadPlanStep("b", "步骤 B", ("a",), "B 完成"),
    )
    with pytest.raises(ValueError, match="cycle"):
        build_long_term_plan("p1", "循环计划", cyclic)

    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", steps()))
    with pytest.raises(ValueError, match="only the active"):
        record_step_result(plan, step_id="verify", succeeded=True, evidence=(evidence(),), now=NOW)


def test_failed_step_retries_then_blocks_at_attempt_limit() -> None:
    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", steps()))
    plan = record_step_result(plan, step_id="inspect", succeeded=False, failure_reason="读取失败")
    assert current_plan_step(plan).step_id == "inspect"  # type: ignore[union-attr]
    assert current_plan_step(plan).attempts == 1  # type: ignore[union-attr]

    plan = record_step_result(plan, step_id="inspect", succeeded=False, failure_reason="仍然失败")
    assert plan.status == LongTermPlanStatus.BLOCKED
    assert plan.current_step_id is None


def test_blocked_plan_can_replan_but_has_finite_budget() -> None:
    original = (HeadPlanStep("inspect", "检查", completion_criteria="完成", max_attempts=1),)
    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", original))
    plan = record_step_result(plan, step_id="inspect", succeeded=False, failure_reason="失败")
    replacement = (HeadPlanStep("inspect-alt", "替代检查", completion_criteria="完成"),)

    plan = replan_remaining_steps(plan, replacement_steps=replacement)
    assert plan.version == 2
    assert plan.replan_count == 1
    assert current_plan_step(plan).step_id == "inspect-alt"  # type: ignore[union-attr]


def test_completed_plan_has_no_current_step() -> None:
    one = (HeadPlanStep("done", "完成一步", completion_criteria="有测试证据"),)
    plan = activate_next_step(build_long_term_plan("p1", "单步目标", one))
    plan = record_step_result(plan, step_id="done", succeeded=True, evidence=(evidence(),), now=NOW)

    assert plan.status == LongTermPlanStatus.COMPLETED
    assert current_plan_step(plan) is None
    assert "status=completed" in project_long_term_plan(plan)[0]


def test_active_plan_persists_and_restores_in_head_context(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", steps()))
    asyncio.run(
        save_long_term_plan(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message_id=None,
            plan=plan,
            allow_write=True,
        )
    )

    restored = asyncio.run(load_long_term_plan(repository, user_id="user-1"))
    context = asyncio.run(load_head_event_context(repository, user_id="user-1"))
    other = asyncio.run(load_long_term_plan(repository, user_id="user-2"))

    assert restored is not None and restored.current_step_id == "inspect"
    assert context.long_term_plan is not None
    assert context.long_term_plan.current_step_id == "inspect"
    assert other is None


def test_model_claim_cannot_complete_a_plan_step() -> None:
    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", steps()))
    with pytest.raises(ValueError, match="model claims"):
        record_step_result(
            plan,
            step_id="inspect",
            succeeded=True,
            evidence=(evidence(source=ExecutionEvidenceSource.MODEL_CLAIM),),
            now=NOW,
        )


def test_failed_or_expired_evidence_cannot_complete_a_plan_step() -> None:
    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", steps()))
    with pytest.raises(ValueError, match="failed execution evidence"):
        record_step_result(
            plan,
            step_id="inspect",
            succeeded=True,
            evidence=(evidence(succeeded=False),),
            now=NOW,
        )
    with pytest.raises(ValueError, match="expired execution evidence"):
        record_step_result(
            plan,
            step_id="inspect",
            succeeded=True,
            evidence=(evidence(expires_at=NOW - dt.timedelta(seconds=1)),),
            now=NOW,
        )


def test_explicit_user_confirmation_is_trusted_evidence() -> None:
    plan = activate_next_step(build_long_term_plan("p1", "完成项目修改", steps()))
    plan = record_step_result(
        plan,
        step_id="inspect",
        succeeded=True,
        evidence=(evidence(source=ExecutionEvidenceSource.USER_CONFIRMATION),),
        now=NOW,
    )
    assert plan.steps[0].status == PlanStepStatus.COMPLETED


def test_fresh_confident_world_event_can_complete_active_step() -> None:
    plan = activate_next_step(build_long_term_plan("p1", "complete project", steps()))
    model = HeadWorldModel(
        entities=(WorldEntity("project", "software", "Project"),),
        events=(
            WorldEvent("test-pass", "test", ("project",), NOW.isoformat(), "test_runner", "tests passed", 0.9),
        ),
    )

    completed = record_step_result_from_world_events(
        plan, step_id="inspect", world_model=model, event_ids=("test-pass",), now=NOW
    )

    assert completed.steps[0].status == PlanStepStatus.COMPLETED
    assert completed.steps[0].evidence[0].source is ExecutionEvidenceSource.WORLD_EVENT


def test_stale_or_low_confidence_world_event_cannot_complete_step() -> None:
    model = HeadWorldModel(
        entities=(WorldEntity("project", "software", "Project"),),
        events=(
            WorldEvent("old", "test", ("project",), (NOW - dt.timedelta(days=31)).isoformat(), "test_runner", "old", 0.9),
            WorldEvent("weak", "test", ("project",), NOW.isoformat(), "test_runner", "weak", 0.7),
        ),
    )
    with pytest.raises(ValueError, match="stale event"):
        build_world_event_evidence(model, event_ids=("old",), now=NOW)
    with pytest.raises(ValueError, match="confidence"):
        build_world_event_evidence(model, event_ids=("weak",), now=NOW)


def test_completed_plan_remains_auditable_after_evidence_expiry(tmp_path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    session = asyncio.run(repository.ensure_session(user_id="user-1", client_session_id="s1"))
    one = (HeadPlanStep("done", "完成一步", completion_criteria="有测试证据"),)
    plan = activate_next_step(build_long_term_plan("p1", "单步目标", one))
    plan = record_step_result(
        plan,
        step_id="done",
        succeeded=True,
        evidence=(evidence(expires_at=NOW + dt.timedelta(minutes=1)),),
        now=NOW,
    )
    asyncio.run(
        save_long_term_plan(
            repository,
            user_id="user-1",
            session_id=session.id,
            source_message_id=None,
            plan=plan,
            allow_write=True,
        )
    )
    restored = asyncio.run(load_long_term_plan(repository, user_id="user-1"))
    assert restored is not None and restored.status == LongTermPlanStatus.COMPLETED
