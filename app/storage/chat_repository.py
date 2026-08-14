from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol

from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets
from app.services.model_audit import text_hash


DEFAULT_STORAGE_DIR = PROJECT_ROOT / "logs" / "storage"
MessageRole = Literal["user", "assistant"]
RelationshipRole = Literal[
    "owner",
    "owner_friend",
    "owner_relative",
    "friend",
    "stranger",
    "blocked",
]
RelationshipClaimStatus = Literal["pending", "approved", "rejected"]


_JSONL_LOCKS_GUARD = threading.Lock()
_JSONL_LOCKS: dict[Path, object] = {}


def _jsonl_lock(path: Path):
    key = path.resolve(strict=False)
    with _JSONL_LOCKS_GUARD:
        lock = _JSONL_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _JSONL_LOCKS[key] = lock
        return lock


def new_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class SessionRecord:
    id: str
    user_id: str
    client_session_id: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MessageRecord:
    id: str
    session_id: str
    user_id: str
    role: MessageRole
    content: str
    content_hash: str
    model_invocation_id: str | None
    created_at: str


@dataclass(frozen=True)
class ModelInvocationRecord:
    id: str
    session_id: str
    user_id: str
    provider: str
    model: str
    used_live_api: bool
    fallback_used: bool
    latency_ms: float
    prompt_hash: str
    response_hash: str
    error: str | None
    request_metadata_json: dict[str, str]
    created_at: str


@dataclass(frozen=True)
class PersonaEvaluationRecord:
    id: str
    message_id: str
    model_invocation_id: str | None
    passed: bool
    score: float | None
    evaluator_provider: str
    evaluator_model: str
    reasons_json: dict[str, object]
    created_at: str


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    user_id: str
    session_id: str | None
    memory_type: str
    content: str
    content_hash: str
    source_message_id: str | None
    confidence: float | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ContactRecord:
    id: str
    display_name: str
    relationship_role: RelationshipRole
    authority_level: int
    affection_level: int
    trust_level: int
    notes: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PlatformIdentityRecord:
    id: str
    contact_id: str
    platform: str
    platform_user_id: str
    platform_group_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RelationshipClaimRecord:
    id: str
    platform: str
    platform_user_id: str
    claimed_role: RelationshipRole
    claimed_name: str
    evidence_text: str
    status: RelationshipClaimStatus
    reviewer_platform_user_id: str | None
    created_at: str
    updated_at: str


class ChatRepository(Protocol):
    async def ensure_session(self, *, user_id: str, client_session_id: str) -> SessionRecord:
        pass

    async def save_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: MessageRole,
        content: str,
        model_invocation_id: str | None = None,
    ) -> MessageRecord:
        pass

    async def save_model_invocation(
        self,
        *,
        session_id: str,
        user_id: str,
        provider: str,
        model: str,
        used_live_api: bool,
        fallback_used: bool,
        latency_ms: float,
        prompt_hash: str,
        response_hash: str,
        error: str | None,
        request_metadata_json: dict[str, str],
    ) -> ModelInvocationRecord:
        pass

    async def save_persona_evaluation(
        self,
        *,
        message_id: str,
        model_invocation_id: str | None,
        passed: bool,
        score: float | None,
        evaluator_provider: str,
        evaluator_model: str,
        reasons_json: dict[str, object],
    ) -> PersonaEvaluationRecord:
        pass

    async def save_memory(
        self,
        *,
        user_id: str,
        session_id: str | None,
        memory_type: str,
        content: str,
        source_message_id: str | None = None,
        confidence: float | None = None,
    ) -> MemoryRecord:
        pass

    async def list_memories(
        self,
        *,
        user_id: str,
        memory_types: list[str] | None = None,
        limit: int = 8,
    ) -> list[MemoryRecord]:
        pass

    async def delete_memory(self, *, user_id: str, memory_id: str) -> bool:
        pass

    async def list_recent_messages(self, *, session_id: str, limit: int = 8) -> list[MessageRecord]:
        pass

    async def list_recent_messages_by_user(self, *, user_id: str, limit: int = 12) -> list[MessageRecord]:
        pass

    async def list_recent_user_ids(self, *, limit: int = 20) -> list[str]:
        pass

    async def resolve_contact(
        self,
        *,
        platform: str,
        platform_user_id: str,
        platform_group_id: str | None = None,
        display_name: str = "",
        owner_platform_user_ids: set[str] | None = None,
    ) -> ContactRecord:
        pass

    async def list_contacts(self, *, limit: int = 50) -> list[ContactRecord]:
        pass

    async def update_contact_relationship(
        self,
        *,
        platform: str,
        platform_user_id: str,
        relationship_role: RelationshipRole,
        display_name: str = "",
        changed_by_platform_user_id: str | None = None,
        reason: str = "",
    ) -> ContactRecord:
        pass

    async def save_relationship_claim(
        self,
        *,
        platform: str,
        platform_user_id: str,
        claimed_role: RelationshipRole,
        claimed_name: str,
        evidence_text: str,
    ) -> RelationshipClaimRecord:
        pass

    async def list_relationship_claims(
        self,
        *,
        status: RelationshipClaimStatus = "pending",
        limit: int = 20,
    ) -> list[RelationshipClaimRecord]:
        pass

    async def review_relationship_claim(
        self,
        *,
        claim_id: str,
        approved: bool,
        reviewer_platform_user_id: str,
    ) -> RelationshipClaimRecord | None:
        pass


class JsonlChatRepository:
    def __init__(self, storage_dir: Path = DEFAULT_STORAGE_DIR) -> None:
        self.storage_dir = storage_dir
        self.sessions_path = storage_dir / "sessions.jsonl"
        self.messages_path = storage_dir / "messages.jsonl"
        self.model_invocations_path = storage_dir / "model_invocations.jsonl"
        self.persona_evaluations_path = storage_dir / "persona_evaluations.jsonl"
        self.memories_path = storage_dir / "memories.jsonl"
        self.contacts_path = storage_dir / "contacts.jsonl"
        self.platform_identities_path = storage_dir / "platform_identities.jsonl"
        self.relationship_events_path = storage_dir / "relationship_events.jsonl"
        self.relationship_claims_path = storage_dir / "relationship_claims.jsonl"

    async def ensure_session(self, *, user_id: str, client_session_id: str) -> SessionRecord:
        with _jsonl_lock(self.sessions_path):
            existing = self._find_session(user_id=user_id, client_session_id=client_session_id)
            if existing:
                return existing
            timestamp = utc_now()
            record = SessionRecord(
                id=new_uuid(),
                user_id=user_id,
                client_session_id=client_session_id,
                created_at=timestamp,
                updated_at=timestamp,
            )
            self._append(self.sessions_path, asdict(record))
            return record

    async def save_message(
        self,
        *,
        session_id: str,
        user_id: str,
        role: MessageRole,
        content: str,
        model_invocation_id: str | None = None,
    ) -> MessageRecord:
        safe_content = redact_secrets(content)
        record = MessageRecord(
            id=new_uuid(),
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=safe_content,
            content_hash=text_hash(safe_content),
            model_invocation_id=model_invocation_id,
            created_at=utc_now(),
        )
        self._append(self.messages_path, asdict(record))
        return record

    async def save_model_invocation(
        self,
        *,
        session_id: str,
        user_id: str,
        provider: str,
        model: str,
        used_live_api: bool,
        fallback_used: bool,
        latency_ms: float,
        prompt_hash: str,
        response_hash: str,
        error: str | None,
        request_metadata_json: dict[str, str],
    ) -> ModelInvocationRecord:
        record = ModelInvocationRecord(
            id=new_uuid(),
            session_id=session_id,
            user_id=user_id,
            provider=provider,
            model=model,
            used_live_api=used_live_api,
            fallback_used=fallback_used,
            latency_ms=round(latency_ms, 2),
            prompt_hash=prompt_hash,
            response_hash=response_hash,
            error=redact_secrets(error) if error else None,
            request_metadata_json=request_metadata_json,
            created_at=utc_now(),
        )
        self._append(self.model_invocations_path, asdict(record))
        return record

    async def save_persona_evaluation(
        self,
        *,
        message_id: str,
        model_invocation_id: str | None,
        passed: bool,
        score: float | None,
        evaluator_provider: str,
        evaluator_model: str,
        reasons_json: dict[str, object],
    ) -> PersonaEvaluationRecord:
        record = PersonaEvaluationRecord(
            id=new_uuid(),
            message_id=message_id,
            model_invocation_id=model_invocation_id,
            passed=passed,
            score=score,
            evaluator_provider=evaluator_provider,
            evaluator_model=evaluator_model,
            reasons_json=reasons_json,
            created_at=utc_now(),
        )
        self._append(self.persona_evaluations_path, asdict(record))
        return record

    async def save_memory(
        self,
        *,
        user_id: str,
        session_id: str | None,
        memory_type: str,
        content: str,
        source_message_id: str | None = None,
        confidence: float | None = None,
    ) -> MemoryRecord:
        safe_content = redact_secrets(content)
        timestamp = utc_now()
        record = MemoryRecord(
            id=new_uuid(),
            user_id=user_id,
            session_id=session_id,
            memory_type=memory_type,
            content=safe_content,
            content_hash=text_hash(safe_content),
            source_message_id=source_message_id,
            confidence=confidence,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._append(self.memories_path, asdict(record))
        return record

    async def list_memories(
        self,
        *,
        user_id: str,
        memory_types: list[str] | None = None,
        limit: int = 8,
    ) -> list[MemoryRecord]:
        type_filter = set(memory_types or [])
        include_internal = bool(type_filter)
        records = [
            MemoryRecord(**item)
            for item in self._read_jsonl(self.memories_path)
            if item.get("user_id") == user_id
            and (not type_filter or item.get("memory_type") in type_filter)
            and (include_internal or not str(item.get("memory_type") or "").startswith("head_"))
        ]
        return records[-limit:]

    async def delete_memory(self, *, user_id: str, memory_id: str) -> bool:
        with _jsonl_lock(self.memories_path):
            items = self._read_jsonl(self.memories_path)
            kept = [
                item
                for item in items
                if not (item.get("id") == memory_id and item.get("user_id") == user_id)
            ]
            if len(kept) == len(items):
                return False
            self.memories_path.parent.mkdir(parents=True, exist_ok=True)
            self.memories_path.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in kept),
                encoding="utf-8",
            )
            return True

    async def list_recent_messages(self, *, session_id: str, limit: int = 8) -> list[MessageRecord]:
        records = [
            MessageRecord(**item)
            for item in self._read_jsonl(self.messages_path)
            if item.get("session_id") == session_id
        ]
        return records[-limit:]

    async def list_recent_messages_by_user(self, *, user_id: str, limit: int = 12) -> list[MessageRecord]:
        records = [
            MessageRecord(**item)
            for item in self._read_jsonl(self.messages_path)
            if item.get("user_id") == user_id
        ]
        return records[-limit:]

    async def list_recent_user_ids(self, *, limit: int = 20) -> list[str]:
        seen: list[str] = []
        for item in reversed(self._read_jsonl(self.messages_path)):
            user_id = str(item.get("user_id") or "")
            if user_id and user_id not in seen:
                seen.append(user_id)
            if len(seen) >= limit:
                break
        return seen

    async def resolve_contact(
        self,
        *,
        platform: str,
        platform_user_id: str,
        platform_group_id: str | None = None,
        display_name: str = "",
        owner_platform_user_ids: set[str] | None = None,
    ) -> ContactRecord:
        normalized_platform = platform.strip().lower()
        normalized_user_id = platform_user_id.strip()
        for identity in self._read_jsonl(self.platform_identities_path):
            if (
                identity.get("platform") == normalized_platform
                and identity.get("platform_user_id") == normalized_user_id
            ):
                contact = self._find_contact_by_id(str(identity["contact_id"]))
                if contact:
                    return contact

        timestamp = utc_now()
        owner_ids = owner_platform_user_ids or set()
        is_owner = normalized_user_id in owner_ids
        role: RelationshipRole = "owner" if is_owner else "stranger"
        contact = ContactRecord(
            id=new_uuid(),
            display_name=display_name.strip() or normalized_user_id,
            relationship_role=role,
            authority_level=100 if is_owner else 10,
            affection_level=100 if is_owner else 10,
            trust_level=100 if is_owner else 10,
            notes="auto-created from platform identity",
            created_at=timestamp,
            updated_at=timestamp,
        )
        identity = PlatformIdentityRecord(
            id=new_uuid(),
            contact_id=contact.id,
            platform=normalized_platform,
            platform_user_id=normalized_user_id,
            platform_group_id=platform_group_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._append(self.contacts_path, asdict(contact))
        self._append(self.platform_identities_path, asdict(identity))
        return contact

    async def list_contacts(self, *, limit: int = 50) -> list[ContactRecord]:
        rows = self._latest_contacts_by_id()
        records = [contact_record_from_mapping(item) for item in rows.values()]
        records.sort(key=lambda item: item.updated_at)
        return records[-limit:]

    async def update_contact_relationship(
        self,
        *,
        platform: str,
        platform_user_id: str,
        relationship_role: RelationshipRole,
        display_name: str = "",
        changed_by_platform_user_id: str | None = None,
        reason: str = "",
    ) -> ContactRecord:
        existing = await self.resolve_contact(platform=platform, platform_user_id=platform_user_id)
        timestamp = utc_now()
        role = relationship_role
        contact = ContactRecord(
            id=existing.id,
            display_name=display_name.strip() or existing.display_name,
            relationship_role=role,
            authority_level=relationship_authority_level(role),
            affection_level=relationship_affection_level(role),
            trust_level=relationship_trust_level(role),
            notes=reason.strip() or existing.notes,
            created_at=existing.created_at,
            updated_at=timestamp,
        )
        self._append(self.contacts_path, asdict(contact))
        self._append(
            self.relationship_events_path,
            {
                "id": new_uuid(),
                "contact_id": contact.id,
                "old_role": existing.relationship_role,
                "new_role": contact.relationship_role,
                "changed_by_platform_user_id": changed_by_platform_user_id,
                "reason": reason,
                "created_at": timestamp,
            },
        )
        return contact

    async def save_relationship_claim(
        self,
        *,
        platform: str,
        platform_user_id: str,
        claimed_role: RelationshipRole,
        claimed_name: str,
        evidence_text: str,
    ) -> RelationshipClaimRecord:
        normalized_platform = platform.strip().lower()
        normalized_user_id = platform_user_id.strip()
        timestamp = utc_now()
        for row in reversed(list(self._latest_claims_by_id().values())):
            if (
                row.get("platform") == normalized_platform
                and row.get("platform_user_id") == normalized_user_id
                and row.get("status") == "pending"
            ):
                return relationship_claim_from_mapping(row)
        record = RelationshipClaimRecord(
            id=new_uuid(),
            platform=normalized_platform,
            platform_user_id=normalized_user_id,
            claimed_role=claimed_role,
            claimed_name=claimed_name.strip(),
            evidence_text=redact_secrets(evidence_text),
            status="pending",
            reviewer_platform_user_id=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._append(self.relationship_claims_path, asdict(record))
        return record

    async def list_relationship_claims(
        self,
        *,
        status: RelationshipClaimStatus = "pending",
        limit: int = 20,
    ) -> list[RelationshipClaimRecord]:
        records = [
            relationship_claim_from_mapping(row)
            for row in self._latest_claims_by_id().values()
            if row.get("status") == status
        ]
        return records[-limit:]

    async def review_relationship_claim(
        self,
        *,
        claim_id: str,
        approved: bool,
        reviewer_platform_user_id: str,
    ) -> RelationshipClaimRecord | None:
        rows = self._read_jsonl(self.relationship_claims_path)
        selected = None
        timestamp = utc_now()
        for row in rows:
            if row.get("id") == claim_id:
                selected = {
                    **row,
                    "status": "approved" if approved else "rejected",
                    "reviewer_platform_user_id": reviewer_platform_user_id,
                    "updated_at": timestamp,
                }
        if selected is None:
            return None
        self._append(self.relationship_claims_path, selected)
        return relationship_claim_from_mapping(selected)

    def _find_session(self, *, user_id: str, client_session_id: str) -> SessionRecord | None:
        for item in self._read_jsonl(self.sessions_path):
            if item.get("user_id") == user_id and item.get("client_session_id") == client_session_id:
                return SessionRecord(**item)
        return None

    def _find_contact_by_id(self, contact_id: str) -> ContactRecord | None:
        for item in reversed(self._read_jsonl(self.contacts_path)):
            if item.get("id") == contact_id:
                return contact_record_from_mapping(item)
        return None

    def _latest_contacts_by_id(self) -> dict[str, dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
        for item in self._read_jsonl(self.contacts_path):
            rows[str(item["id"])] = item
        return rows

    def _latest_claims_by_id(self) -> dict[str, dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
        for item in self._read_jsonl(self.relationship_claims_path):
            rows[str(item["id"])] = item
        return rows

    def _read_jsonl(self, path: Path) -> list[dict[str, str]]:
        with _jsonl_lock(path):
            if not path.exists():
                return []
            return [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line
            ]

    def _append(self, path: Path, data: dict[str, object]) -> None:
        with _jsonl_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(data, ensure_ascii=False) + "\n")


def contact_record_from_mapping(item: dict[str, object]) -> ContactRecord:
    return ContactRecord(
        id=str(item["id"]),
        display_name=str(item["display_name"]),
        relationship_role=relationship_role(str(item["relationship_role"])),
        authority_level=int(item["authority_level"]),
        affection_level=int(item["affection_level"]),
        trust_level=int(item["trust_level"]),
        notes=str(item.get("notes") or ""),
        created_at=str(item["created_at"]),
        updated_at=str(item["updated_at"]),
    )


def relationship_role(value: str) -> RelationshipRole:
    if value not in {"owner", "owner_friend", "owner_relative", "friend", "stranger", "blocked"}:
        return "stranger"
    return value  # type: ignore[return-value]


def relationship_claim_status(value: str) -> RelationshipClaimStatus:
    if value not in {"pending", "approved", "rejected"}:
        return "pending"
    return value  # type: ignore[return-value]


def relationship_claim_from_mapping(item: dict[str, object]) -> RelationshipClaimRecord:
    return RelationshipClaimRecord(
        id=str(item["id"]),
        platform=str(item["platform"]),
        platform_user_id=str(item["platform_user_id"]),
        claimed_role=relationship_role(str(item["claimed_role"])),
        claimed_name=str(item.get("claimed_name") or ""),
        evidence_text=str(item.get("evidence_text") or ""),
        status=relationship_claim_status(str(item["status"])),
        reviewer_platform_user_id=(
            str(item["reviewer_platform_user_id"])
            if item.get("reviewer_platform_user_id") is not None
            else None
        ),
        created_at=str(item["created_at"]),
        updated_at=str(item["updated_at"]),
    )


def relationship_authority_level(role: RelationshipRole) -> int:
    return {
        "owner": 100,
        "owner_relative": 45,
        "owner_friend": 35,
        "friend": 25,
        "stranger": 10,
        "blocked": 0,
    }[role]


def relationship_affection_level(role: RelationshipRole) -> int:
    return {
        "owner": 100,
        "owner_relative": 55,
        "owner_friend": 40,
        "friend": 30,
        "stranger": 10,
        "blocked": 0,
    }[role]


def relationship_trust_level(role: RelationshipRole) -> int:
    return {
        "owner": 100,
        "owner_relative": 55,
        "owner_friend": 40,
        "friend": 25,
        "stranger": 10,
        "blocked": 0,
    }[role]
