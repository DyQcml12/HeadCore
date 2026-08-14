from __future__ import annotations

from app.knowledge.models import (
    KnowledgeActor,
    MemoryCandidate,
    MemoryDecisionKind,
    MemoryRecord,
    MemoryScope,
)


MIN_OBSERVATION_QUALITY = 0.65


def evaluate_candidate(candidate: MemoryCandidate, actor: KnowledgeActor) -> tuple[MemoryDecisionKind, str]:
    if actor.relationship_type == "blocked":
        return MemoryDecisionKind.REJECT, "blocked profiles cannot write long-term memory"
    if not actor.can_write_long_term_memory:
        return MemoryDecisionKind.REJECT, "actor lacks long-term memory permission"
    if candidate.profile_id != actor.profile_id and not (actor.is_admin and actor.verified):
        return MemoryDecisionKind.REJECT, "actor cannot write another profile"
    if candidate.observation_quality is not None and candidate.observation_quality < MIN_OBSERVATION_QUALITY:
        return MemoryDecisionKind.REJECT, "observation quality is below the persistence threshold"
    if candidate.changes_authority and not (actor.is_admin and actor.verified):
        return MemoryDecisionKind.REVIEW, "authority or relationship changes require verified admin review"
    if candidate.scope == MemoryScope.ADMIN_PRIVATE and not (actor.is_admin and actor.verified):
        return MemoryDecisionKind.REVIEW, "admin-private memory requires verified admin review"
    return MemoryDecisionKind.APPROVE, "candidate is eligible for lifecycle review"


def can_project(record: MemoryRecord, actor: KnowledgeActor) -> bool:
    if actor.relationship_type == "blocked":
        return False
    if record.scope == MemoryScope.ADMIN_PRIVATE:
        return actor.is_admin and actor.verified
    if record.profile_id != actor.profile_id:
        return False
    if record.scope == MemoryScope.PERSONA_SPECIFIC:
        return bool(record.persona_id and record.persona_id == actor.persona_id)
    return True
