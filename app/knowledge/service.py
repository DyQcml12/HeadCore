from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Callable
from uuid import uuid4

from app.knowledge.models import (
    AuditEvent,
    EntityNotFoundError,
    InvalidStateTransitionError,
    KnowledgeActor,
    MemoryCandidate,
    MemoryDecision,
    MemoryDecisionKind,
    MemoryProjection,
    MemoryRecord,
    MemoryState,
    PortraitPatch,
)
from app.knowledge.policy import can_project, evaluate_candidate
from app.knowledge.repository import KnowledgeRepository


class KnowledgeLifecycleService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def submit(self, patch: PortraitPatch, *, actor: KnowledgeActor) -> MemoryCandidate:
        if patch.idempotency_key:
            existing = await self._repository.get_candidate_by_idempotency_key(
                profile_id=patch.profile_id,
                idempotency_key=patch.idempotency_key,
            )
            if existing is not None:
                return existing
        now = self._clock()
        candidate = MemoryCandidate(
            id=self._id_factory(),
            profile_id=patch.profile_id,
            key=patch.key.strip(),
            value=patch.value.strip(),
            scope=patch.scope,
            source_type=patch.source_type.strip(),
            source_id=patch.source_id.strip(),
            confidence=patch.confidence,
            created_at=now,
            persona_id=patch.persona_id,
            expires_at=patch.expires_at,
            observation_quality=patch.observation_quality,
            changes_authority=patch.changes_authority,
            idempotency_key=patch.idempotency_key,
        )
        self._validate_candidate(candidate)
        await self._repository.add_candidate(candidate)
        await self._audit("candidate", candidate.id, "submitted", actor.profile_id, "candidate submitted", now)
        policy_kind, policy_reason = evaluate_candidate(candidate, actor)
        if policy_kind != MemoryDecisionKind.APPROVE:
            if policy_kind == MemoryDecisionKind.REJECT:
                candidate = await self._repository.update_candidate_state(
                    candidate.id, MemoryState.DELETED
                )
            await self._audit("candidate", candidate.id, policy_kind.value, actor.profile_id, policy_reason, now)
        return candidate

    async def decide(self, candidate_id: str, decision: MemoryDecision) -> MemoryRecord | None:
        candidate = await self._repository.get_candidate(candidate_id)
        if candidate is None:
            raise EntityNotFoundError(f"candidate not found: {candidate_id}")
        if candidate.state != MemoryState.CANDIDATE:
            raise InvalidStateTransitionError(f"candidate is already {candidate.state.value}")

        reviewer = KnowledgeActor(
            profile_id=decision.decided_by_profile_id,
            verified=True,
            is_admin=True,
        )
        policy_kind, policy_reason = evaluate_candidate(candidate, reviewer)
        if decision.kind == MemoryDecisionKind.APPROVE and policy_kind == MemoryDecisionKind.REJECT:
            raise InvalidStateTransitionError(policy_reason)
        if decision.kind != MemoryDecisionKind.APPROVE:
            terminal = MemoryState.DELETED if decision.kind == MemoryDecisionKind.REJECT else MemoryState.CANDIDATE
            if terminal != MemoryState.CANDIDATE:
                await self._repository.update_candidate_state(candidate.id, terminal)
            await self._audit(
                "candidate", candidate.id, decision.kind.value, decision.decided_by_profile_id,
                decision.reason, decision.decided_at,
            )
            return None

        conflicts = await self._active_conflicts(candidate, decision.decided_at)
        if conflicts and not decision.supersede_conflicts:
            await self._audit(
                "candidate", candidate.id, "review", decision.decided_by_profile_id,
                "conflicting active memory requires explicit supersede", decision.decided_at,
                {"conflict_ids": [record.id for record in conflicts]},
            )
            return None

        superseded_records = tuple(
            replace(
                conflict,
                state=MemoryState.SUPERSEDED,
                updated_at=decision.decided_at,
                state_reason=f"superseded by candidate {candidate.id}",
            )
            for conflict in conflicts
        )

        record = MemoryRecord(
            id=self._id_factory(),
            candidate_id=candidate.id,
            profile_id=candidate.profile_id,
            key=candidate.key,
            value=candidate.value,
            scope=candidate.scope,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
            confidence=candidate.confidence,
            state=MemoryState.ACTIVE,
            created_at=decision.decided_at,
            updated_at=decision.decided_at,
            persona_id=candidate.persona_id,
            expires_at=candidate.expires_at,
            supersedes_id=conflicts[0].id if conflicts else None,
            state_reason=decision.reason,
        )
        audit_events = tuple(
            AuditEvent(
                id=self._id_factory(), entity_type="memory", entity_id=updated.id,
                action="superseded", actor_profile_id=decision.decided_by_profile_id,
                reason=updated.state_reason, occurred_at=decision.decided_at,
                details={"candidate_id": candidate.id},
            )
            for updated in superseded_records
        ) + (
            AuditEvent(
                id=self._id_factory(), entity_type="memory", entity_id=record.id,
                action="activated", actor_profile_id=decision.decided_by_profile_id,
                reason=decision.reason, occurred_at=decision.decided_at,
                details={"candidate_id": candidate.id},
            ),
        )
        await self._repository.apply_approval(
            candidate_id=candidate.id,
            superseded_records=superseded_records,
            record=record,
            audit_events=audit_events,
        )
        return record

    async def revoke(self, record_id: str, *, actor: KnowledgeActor, reason: str) -> MemoryRecord:
        return await self._transition(record_id, MemoryState.REVOKED, actor, reason)

    async def delete(self, record_id: str, *, actor: KnowledgeActor, reason: str) -> MemoryRecord:
        return await self._transition(record_id, MemoryState.DELETED, actor, reason)

    async def expire_due(self, *, profile_id: str, now: datetime | None = None) -> tuple[MemoryRecord, ...]:
        effective_now = now or self._clock()
        expired: list[MemoryRecord] = []
        for record in await self._repository.list_records(profile_id=profile_id):
            if record.state == MemoryState.ACTIVE and record.expires_at is not None and record.expires_at <= effective_now:
                updated = replace(
                    record, state=MemoryState.EXPIRED, updated_at=effective_now,
                    state_reason="memory reached expires_at",
                )
                await self._repository.update_record(updated)
                await self._audit("memory", record.id, "expired", "system", updated.state_reason, effective_now)
                expired.append(updated)
        return tuple(expired)

    async def project(self, *, actor: KnowledgeActor, now: datetime | None = None) -> tuple[MemoryProjection, ...]:
        effective_now = now or self._clock()
        await self.expire_due(profile_id=actor.profile_id, now=effective_now)
        records = await self._repository.list_records(profile_id=actor.profile_id)
        return tuple(
            MemoryProjection(
                record_id=record.id,
                profile_id=record.profile_id,
                key=record.key,
                value=record.value,
                scope=record.scope,
                confidence=record.confidence,
                persona_id=record.persona_id,
                expires_at=record.expires_at,
            )
            for record in records
            if record.state == MemoryState.ACTIVE and can_project(record, actor)
        )

    async def _transition(
        self, record_id: str, target: MemoryState, actor: KnowledgeActor, reason: str,
    ) -> MemoryRecord:
        record = await self._repository.get_record(record_id)
        if record is None:
            raise EntityNotFoundError(f"memory not found: {record_id}")
        if record.state != MemoryState.ACTIVE:
            raise InvalidStateTransitionError(f"cannot transition {record.state.value} to {target.value}")
        if actor.profile_id != record.profile_id and not (actor.is_admin and actor.verified):
            raise PermissionError("actor cannot change another profile's memory")
        now = self._clock()
        updated = replace(record, state=target, updated_at=now, state_reason=reason)
        await self._repository.update_record(updated)
        await self._audit("memory", record.id, target.value, actor.profile_id, reason, now)
        return updated

    async def _active_conflicts(self, candidate: MemoryCandidate, now: datetime) -> tuple[MemoryRecord, ...]:
        records = await self._repository.list_records(profile_id=candidate.profile_id)
        return tuple(
            record
            for record in records
            if record.state == MemoryState.ACTIVE
            and (record.expires_at is None or record.expires_at > now)
            and record.key == candidate.key
            and record.scope == candidate.scope
            and record.persona_id == candidate.persona_id
            and record.value != candidate.value
        )

    async def _audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_profile_id: str,
        reason: str,
        occurred_at: datetime,
        details: dict[str, object] | None = None,
    ) -> None:
        await self._repository.append_audit(
            AuditEvent(
                id=self._id_factory(), entity_type=entity_type, entity_id=entity_id,
                action=action, actor_profile_id=actor_profile_id, reason=reason,
                occurred_at=occurred_at, details=details or {},
            )
        )

    @staticmethod
    def _validate_candidate(candidate: MemoryCandidate) -> None:
        if not candidate.profile_id or not candidate.key or not candidate.value:
            raise ValueError("profile_id, key, and value are required")
        if not candidate.source_type or not candidate.source_id:
            raise ValueError("memory provenance is required")
        if not 0.0 <= candidate.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if candidate.observation_quality is not None and not 0.0 <= candidate.observation_quality <= 1.0:
            raise ValueError("observation_quality must be between 0 and 1")
        if candidate.expires_at is not None and candidate.expires_at <= candidate.created_at:
            raise ValueError("expires_at must be after created_at")
