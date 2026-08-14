from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class MemoryState(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    EXPIRED = "expired"
    DELETED = "deleted"


class MemoryScope(StrEnum):
    ADMIN_PRIVATE = "admin_private"
    PROFILE_PRIVATE = "profile_private"
    PERSONA_SPECIFIC = "persona_specific"
    SAFE_PREFERENCE = "safe_preference"


class MemoryDecisionKind(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REVIEW = "review"


@dataclass(frozen=True)
class KnowledgeActor:
    profile_id: str
    account_id: str | None = None
    persona_id: str | None = None
    relationship_type: str = "normal_friend"
    verified: bool = False
    is_admin: bool = False
    can_write_long_term_memory: bool = True


@dataclass(frozen=True)
class MemoryCandidate:
    id: str
    profile_id: str
    key: str
    value: str
    scope: MemoryScope
    source_type: str
    source_id: str
    confidence: float
    created_at: datetime
    persona_id: str | None = None
    expires_at: datetime | None = None
    observation_quality: float | None = None
    changes_authority: bool = False
    idempotency_key: str | None = None
    state: MemoryState = MemoryState.CANDIDATE


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    candidate_id: str
    profile_id: str
    key: str
    value: str
    scope: MemoryScope
    source_type: str
    source_id: str
    confidence: float
    state: MemoryState
    created_at: datetime
    updated_at: datetime
    persona_id: str | None = None
    expires_at: datetime | None = None
    supersedes_id: str | None = None
    state_reason: str = ""


@dataclass(frozen=True)
class PortraitPatch:
    profile_id: str
    key: str
    value: str
    scope: MemoryScope
    source_type: str
    source_id: str
    confidence: float
    persona_id: str | None = None
    expires_at: datetime | None = None
    observation_quality: float | None = None
    changes_authority: bool = False
    idempotency_key: str | None = None


@dataclass(frozen=True)
class MemoryDecision:
    kind: MemoryDecisionKind
    reason: str
    decided_by_profile_id: str
    decided_at: datetime
    supersede_conflicts: bool = False


@dataclass(frozen=True)
class MemoryProjection:
    record_id: str
    profile_id: str
    key: str
    value: str
    scope: MemoryScope
    confidence: float
    persona_id: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class AuditEvent:
    id: str
    entity_type: str
    entity_id: str
    action: str
    actor_profile_id: str
    reason: str
    occurred_at: datetime
    details: Mapping[str, Any] = field(default_factory=dict)


class KnowledgeLifecycleError(ValueError):
    pass


class EntityNotFoundError(KnowledgeLifecycleError):
    pass


class InvalidStateTransitionError(KnowledgeLifecycleError):
    pass
