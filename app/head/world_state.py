from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.world.context import WorldContextProjection


class WorldKnowledgeStatus(StrEnum):
    IDLE = "idle"
    KNOWN = "known"
    UNCERTAIN = "uncertain"
    NEEDS_INPUT = "needs_input"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class HeadWorldState:
    status: WorldKnowledgeStatus
    tool_intent: str
    can_answer: bool
    requires_clarification: bool
    evidence_source_ids: tuple[str, ...]
    conflict_fields: tuple[str, ...]
    reason: str


def world_state_uncertainties(state: HeadWorldState) -> tuple[str, ...]:
    """Convert non-ready world knowledge into bounded HeadCore uncertainty markers."""
    intent = state.tool_intent or "unknown"
    if state.status == WorldKnowledgeStatus.NEEDS_INPUT:
        return (f"world_input_required:{intent}",)
    if state.status == WorldKnowledgeStatus.UNCERTAIN:
        return (f"world_evidence_uncertain:{intent}",)
    if state.status == WorldKnowledgeStatus.UNAVAILABLE:
        return (f"world_evidence_unavailable:{intent}",)
    return ()


def build_head_world_state(projection: WorldContextProjection) -> HeadWorldState:
    status = projection.status
    conflicts = tuple(conflict.field for conflict in projection.conflicts)
    if status in {"ready", "resolved"}:
        knowledge_status = WorldKnowledgeStatus.KNOWN
        can_answer = bool(projection.source_ids or projection.item_count)
        requires_clarification = False
        reason = "evidence_ready"
    elif status in {"partial", "conflicted", "stale"}:
        knowledge_status = WorldKnowledgeStatus.UNCERTAIN
        can_answer = status in {"partial", "conflicted"} and bool(
            projection.source_ids or projection.item_count
        )
        requires_clarification = False
        reason = f"world_{status}"
    elif status.startswith("needs_") or status == "ambiguous":
        knowledge_status = WorldKnowledgeStatus.NEEDS_INPUT
        can_answer = False
        requires_clarification = True
        reason = status
    elif status in {"not_requested", "not_configured", "proactive_denied"}:
        knowledge_status = WorldKnowledgeStatus.IDLE
        can_answer = False
        requires_clarification = False
        reason = status
    else:
        knowledge_status = WorldKnowledgeStatus.UNAVAILABLE
        can_answer = False
        requires_clarification = status == "not_found"
        reason = status or "unknown_world_status"
    return HeadWorldState(
        status=knowledge_status,
        tool_intent=projection.tool_intent,
        can_answer=can_answer,
        requires_clarification=requires_clarification,
        evidence_source_ids=projection.source_ids,
        conflict_fields=conflicts,
        reason=reason,
    )


def render_head_world_state(state: HeadWorldState) -> str:
    sources = ",".join(state.evidence_source_ids) or "none"
    conflicts = ",".join(state.conflict_fields) or "none"
    return (
        "HeadCore 世界认知状态（内部控制信息）："
        f"status={state.status.value}；intent={state.tool_intent}；"
        f"can_answer={str(state.can_answer).lower()}；"
        f"requires_clarification={str(state.requires_clarification).lower()}；"
        f"sources={sources}；conflicts={conflicts}；reason={state.reason}。"
        "只有 can_answer=true 时才可依据世界证据陈述实时事实；"
        "uncertain 必须保留冲突或不完整性，needs_input 必须追问。"
    )
