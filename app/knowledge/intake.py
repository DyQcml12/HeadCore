from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from app.knowledge.models import KnowledgeActor, MemoryCandidate, MemoryScope, PortraitPatch
from app.knowledge.service import KnowledgeLifecycleService


EligibilityDecision = Literal["allow", "review", "deny"]


@dataclass(frozen=True)
class MemoryCandidateInput:
    profile_id: str
    key: str
    value: str
    scope: MemoryScope
    source_type: str
    source_id: str
    confidence: float
    eligibility: EligibilityDecision
    eligibility_reasons: tuple[str, ...] = ()
    persona_id: str | None = None
    observation_quality: float | None = None
    changes_authority: bool = False


@dataclass(frozen=True)
class MemoryIntakeResult:
    status: Literal["candidate", "review", "rejected"]
    reason: str
    candidate: MemoryCandidate | None = None


class MemoryCandidateIntakeService:
    def __init__(self, lifecycle: KnowledgeLifecycleService) -> None:
        self._lifecycle = lifecycle

    async def submit(
        self,
        value: MemoryCandidateInput,
        *,
        actor: KnowledgeActor,
        identity_bound: bool,
    ) -> MemoryIntakeResult:
        reason = self._reject_reason(value, actor=actor, identity_bound=identity_bound)
        if reason:
            return MemoryIntakeResult(status="rejected", reason=reason)
        candidate = await self._lifecycle.submit(
            PortraitPatch(
                profile_id=value.profile_id,
                key=value.key,
                value=value.value,
                scope=value.scope,
                source_type=value.source_type,
                source_id=value.source_id,
                confidence=value.confidence,
                persona_id=value.persona_id,
                observation_quality=value.observation_quality,
                changes_authority=value.changes_authority,
                idempotency_key=_idempotency_key(value),
            ),
            actor=actor,
        )
        if value.eligibility == "review":
            return MemoryIntakeResult(
                status="review",
                reason=",".join(value.eligibility_reasons) or "perception_review_required",
                candidate=candidate,
            )
        return MemoryIntakeResult(
            status="candidate", reason="awaiting_lifecycle_approval", candidate=candidate
        )

    @staticmethod
    def _reject_reason(
        value: MemoryCandidateInput,
        *,
        actor: KnowledgeActor,
        identity_bound: bool,
    ) -> str:
        if not identity_bound:
            return "identity_unbound"
        if actor.relationship_type == "blocked":
            return "profile_blocked"
        if not actor.can_write_long_term_memory:
            return "memory_write_forbidden"
        if value.profile_id != actor.profile_id and not (actor.is_admin and actor.verified):
            return "profile_mismatch"
        if value.eligibility == "deny":
            return ",".join(value.eligibility_reasons) or "perception_denied"
        if not value.value.strip():
            return "empty_candidate"
        return ""


def _idempotency_key(value: MemoryCandidateInput) -> str:
    payload = "\x1f".join(
        (value.profile_id, value.source_type, value.source_id, value.key)
    )
    return sha256(payload.encode("utf-8")).hexdigest()
