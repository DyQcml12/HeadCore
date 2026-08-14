from __future__ import annotations

import datetime as dt
import inspect
import json
from typing import Any

from app.core.config import Settings
from app.core.security import redact_secrets
from app.services.model_audit import text_hash
from app.storage.chat_repository import (
    ContactRecord,
    MemoryRecord,
    MessageRecord,
    MessageRole,
    ModelInvocationRecord,
    PersonaEvaluationRecord,
    RelationshipClaimRecord,
    RelationshipClaimStatus,
    RelationshipRole,
    SessionRecord,
    contact_record_from_mapping,
    new_uuid,
    relationship_affection_level,
    relationship_authority_level,
    relationship_claim_from_mapping,
    relationship_trust_level,
    utc_now,
)


class MySQLChatRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._validate_settings()

    async def ensure_session(self, *, user_id: str, client_session_id: str) -> SessionRecord:
        existing = await self._fetch_session(user_id=user_id, client_session_id=client_session_id)
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
        await self._execute(
            """
            INSERT INTO sessions (id, user_id, client_session_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.user_id,
                record.client_session_id,
                mysql_datetime(record.created_at),
                mysql_datetime(record.updated_at),
            ),
        )
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
        await self._execute(
            """
            INSERT INTO messages (
                id, session_id, user_id, role, content, content_hash,
                model_invocation_id, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.session_id,
                record.user_id,
                record.role,
                record.content,
                record.content_hash,
                record.model_invocation_id,
                mysql_datetime(record.created_at),
            ),
        )
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
        await self._execute(
            """
            INSERT INTO model_invocations (
                id, session_id, user_id, provider, model, used_live_api,
                fallback_used, latency_ms, prompt_hash, response_hash, error,
                request_metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.session_id,
                record.user_id,
                record.provider,
                record.model,
                record.used_live_api,
                record.fallback_used,
                record.latency_ms,
                record.prompt_hash,
                record.response_hash,
                record.error,
                json.dumps(record.request_metadata_json, ensure_ascii=False),
                mysql_datetime(record.created_at),
            ),
        )
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
        await self._execute(
            """
            INSERT INTO persona_evaluations (
                id, message_id, model_invocation_id, passed, score,
                evaluator_provider, evaluator_model, reasons_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.message_id,
                record.model_invocation_id,
                record.passed,
                record.score,
                record.evaluator_provider,
                record.evaluator_model,
                json.dumps(record.reasons_json, ensure_ascii=False),
                mysql_datetime(record.created_at),
            ),
        )
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
        await self._execute(
            """
            INSERT INTO memories (
                id, user_id, session_id, memory_type, content, content_hash,
                source_message_id, confidence, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.user_id,
                record.session_id,
                record.memory_type,
                record.content,
                record.content_hash,
                record.source_message_id,
                record.confidence,
                mysql_datetime(record.created_at),
                mysql_datetime(record.updated_at),
            ),
        )
        return record

    async def list_memories(
        self,
        *,
        user_id: str,
        memory_types: list[str] | None = None,
        limit: int = 8,
    ) -> list[MemoryRecord]:
        params: list[Any] = [user_id]
        type_clause = ""
        if memory_types:
            placeholders = ", ".join(["%s"] * len(memory_types))
            type_clause = f" AND memory_type IN ({placeholders})"
            params.extend(memory_types)
        else:
            type_clause = " AND LEFT(memory_type, 5) <> 'head_'"
        params.append(limit)
        rows = await self._fetchall(
            f"""
            SELECT id, user_id, session_id, memory_type, content, content_hash,
                   source_message_id, confidence, created_at, updated_at
            FROM memories
            WHERE user_id = %s{type_clause}
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return [
            MemoryRecord(
                id=str(row["id"]),
                user_id=str(row["user_id"]),
                session_id=str(row["session_id"]) if row["session_id"] is not None else None,
                memory_type=str(row["memory_type"]),
                content=str(row["content"]),
                content_hash=str(row["content_hash"]),
                source_message_id=(
                    str(row["source_message_id"])
                    if row["source_message_id"] is not None
                    else None
                ),
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    async def delete_memory(self, *, user_id: str, memory_id: str) -> bool:
        affected_rows = await self._execute(
            """
            DELETE FROM memories
            WHERE id = %s AND user_id = %s
            """,
            (memory_id, user_id),
        )
        return affected_rows > 0

    async def list_recent_messages(self, *, session_id: str, limit: int = 8) -> list[MessageRecord]:
        rows = await self._fetchall(
            """
            SELECT id, session_id, user_id, role, content, content_hash,
                   model_invocation_id, created_at
            FROM messages
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        return [
            MessageRecord(
                id=str(row["id"]),
                session_id=str(row["session_id"]),
                user_id=str(row["user_id"]),
                role=mysql_message_role(row["role"]),
                content=str(row["content"]),
                content_hash=str(row["content_hash"]),
                model_invocation_id=(
                    str(row["model_invocation_id"])
                    if row["model_invocation_id"] is not None
                    else None
                ),
                created_at=str(row["created_at"]),
            )
            for row in reversed(rows)
        ]

    async def list_recent_messages_by_user(self, *, user_id: str, limit: int = 12) -> list[MessageRecord]:
        rows = await self._fetchall(
            """
            SELECT id, session_id, user_id, role, content, content_hash,
                   model_invocation_id, created_at
            FROM messages
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return [
            MessageRecord(
                id=str(row["id"]),
                session_id=str(row["session_id"]),
                user_id=str(row["user_id"]),
                role=mysql_message_role(row["role"]),
                content=str(row["content"]),
                content_hash=str(row["content_hash"]),
                model_invocation_id=(
                    str(row["model_invocation_id"])
                    if row["model_invocation_id"] is not None
                    else None
                ),
                created_at=str(row["created_at"]),
            )
            for row in reversed(rows)
        ]

    async def list_recent_user_ids(self, *, limit: int = 20) -> list[str]:
        rows = await self._fetchall(
            """
            SELECT user_id, MAX(created_at) AS last_message_at
            FROM messages
            GROUP BY user_id
            ORDER BY last_message_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [str(row["user_id"]) for row in rows]

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
        row = await self._fetchone(
            """
            SELECT c.id, c.display_name, c.relationship_role, c.authority_level,
                   c.affection_level, c.trust_level, c.notes, c.created_at, c.updated_at
            FROM contacts c
            INNER JOIN platform_identities p ON p.contact_id = c.id
            WHERE p.platform = %s AND p.platform_user_id = %s
            LIMIT 1
            """,
            (normalized_platform, normalized_user_id),
        )
        if row is not None:
            return contact_record_from_mapping(row)

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
        identity_id = new_uuid()
        await self._execute(
            """
            INSERT INTO contacts (
                id, display_name, relationship_role, authority_level,
                affection_level, trust_level, notes, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                contact.id,
                contact.display_name,
                contact.relationship_role,
                contact.authority_level,
                contact.affection_level,
                contact.trust_level,
                contact.notes,
                mysql_datetime(contact.created_at),
                mysql_datetime(contact.updated_at),
            ),
        )
        await self._execute(
            """
            INSERT INTO platform_identities (
                id, contact_id, platform, platform_user_id,
                platform_group_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                identity_id,
                contact.id,
                normalized_platform,
                normalized_user_id,
                platform_group_id,
                mysql_datetime(timestamp),
                mysql_datetime(timestamp),
            ),
        )
        return contact

    async def list_contacts(self, *, limit: int = 50) -> list[ContactRecord]:
        rows = await self._fetchall(
            """
            SELECT id, display_name, relationship_role, authority_level,
                   affection_level, trust_level, notes, created_at, updated_at
            FROM contacts
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [contact_record_from_mapping(row) for row in reversed(rows)]

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
        contact = ContactRecord(
            id=existing.id,
            display_name=display_name.strip() or existing.display_name,
            relationship_role=relationship_role,
            authority_level=relationship_authority_level(relationship_role),
            affection_level=relationship_affection_level(relationship_role),
            trust_level=relationship_trust_level(relationship_role),
            notes=reason.strip() or existing.notes,
            created_at=existing.created_at,
            updated_at=timestamp,
        )
        await self._execute(
            """
            UPDATE contacts
            SET display_name = %s, relationship_role = %s, authority_level = %s,
                affection_level = %s, trust_level = %s, notes = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                contact.display_name,
                contact.relationship_role,
                contact.authority_level,
                contact.affection_level,
                contact.trust_level,
                contact.notes,
                mysql_datetime(contact.updated_at),
                contact.id,
            ),
        )
        await self._execute(
            """
            INSERT INTO relationship_events (
                id, contact_id, old_role, new_role, changed_by_contact_id, reason, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                new_uuid(),
                contact.id,
                existing.relationship_role,
                contact.relationship_role,
                None,
                reason or changed_by_platform_user_id or "",
                mysql_datetime(timestamp),
            ),
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
        existing = await self._fetchone(
            """
            SELECT id, platform, platform_user_id, claimed_role, claimed_name,
                   evidence_text, status, reviewer_platform_user_id, created_at, updated_at
            FROM relationship_claims
            WHERE platform = %s AND platform_user_id = %s AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (normalized_platform, normalized_user_id),
        )
        if existing is not None:
            return relationship_claim_from_mapping(existing)

        timestamp = utc_now()
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
        await self._execute(
            """
            INSERT INTO relationship_claims (
                id, platform, platform_user_id, claimed_role, claimed_name,
                evidence_text, status, reviewer_platform_user_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.platform,
                record.platform_user_id,
                record.claimed_role,
                record.claimed_name,
                record.evidence_text,
                record.status,
                record.reviewer_platform_user_id,
                mysql_datetime(record.created_at),
                mysql_datetime(record.updated_at),
            ),
        )
        return record

    async def list_relationship_claims(
        self,
        *,
        status: RelationshipClaimStatus = "pending",
        limit: int = 20,
    ) -> list[RelationshipClaimRecord]:
        rows = await self._fetchall(
            """
            SELECT id, platform, platform_user_id, claimed_role, claimed_name,
                   evidence_text, status, reviewer_platform_user_id, created_at, updated_at
            FROM relationship_claims
            WHERE status = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (status, limit),
        )
        return [relationship_claim_from_mapping(row) for row in reversed(rows)]

    async def review_relationship_claim(
        self,
        *,
        claim_id: str,
        approved: bool,
        reviewer_platform_user_id: str,
    ) -> RelationshipClaimRecord | None:
        row = await self._fetchone(
            """
            SELECT id, platform, platform_user_id, claimed_role, claimed_name,
                   evidence_text, status, reviewer_platform_user_id, created_at, updated_at
            FROM relationship_claims
            WHERE id = %s
            LIMIT 1
            """,
            (claim_id,),
        )
        if row is None:
            return None
        timestamp = utc_now()
        status = "approved" if approved else "rejected"
        await self._execute(
            """
            UPDATE relationship_claims
            SET status = %s, reviewer_platform_user_id = %s, updated_at = %s
            WHERE id = %s
            """,
            (status, reviewer_platform_user_id, mysql_datetime(timestamp), claim_id),
        )
        return relationship_claim_from_mapping(
            {
                **row,
                "status": status,
                "reviewer_platform_user_id": reviewer_platform_user_id,
                "updated_at": timestamp,
            }
        )

    async def _fetch_session(self, *, user_id: str, client_session_id: str) -> SessionRecord | None:
        row = await self._fetchone(
            """
            SELECT id, user_id, client_session_id, created_at, updated_at
            FROM sessions
            WHERE user_id = %s AND client_session_id = %s
            LIMIT 1
            """,
            (user_id, client_session_id),
        )
        if row is None:
            return None
        return SessionRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            client_session_id=str(row["client_session_id"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    async def _execute(self, sql: str, params: tuple[Any, ...]) -> int:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(sql, params)
            affected_rows = int(getattr(cursor, "rowcount", 0) or 0)
            await connection.commit()
        finally:
            close_result = cursor.close()
            if inspect.isawaitable(close_result):
                await close_result
            connection.close()
        return affected_rows

    async def _fetchone(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(sql, params)
            row = await cursor.fetchone()
        finally:
            close_result = cursor.close()
            if inspect.isawaitable(close_result):
                await close_result
            connection.close()
        return row

    async def _fetchall(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
        finally:
            close_result = cursor.close()
            if inspect.isawaitable(close_result):
                await close_result
            connection.close()
        return list(rows)

    async def _connect(self) -> Any:
        try:
            import asyncmy
        except ImportError as exc:
            raise RuntimeError(
                "asyncmy is required for STORAGE_BACKEND=mysql. "
                "Install dependencies with `python -m pip install -r requirements.txt`."
            ) from exc

        return await asyncmy.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            db=self.settings.mysql_database,
            charset="utf8mb4",
            autocommit=False,
            cursor_cls=asyncmy.cursors.DictCursor,
        )

    def _validate_settings(self) -> None:
        missing = [
            name
            for name, value in [
                ("MYSQL_DATABASE", self.settings.mysql_database),
                ("MYSQL_USER", self.settings.mysql_user),
                ("MYSQL_PASSWORD", self.settings.mysql_password),
            ]
            if not value
        ]
        if missing:
            raise ValueError(
                "STORAGE_BACKEND=mysql requires non-empty settings: " + ", ".join(missing)
            )


def mysql_datetime(timestamp: str) -> str:
    parsed = dt.datetime.fromisoformat(timestamp)
    return parsed.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def mysql_message_role(value: object) -> MessageRole:
    role = str(value)
    if role not in {"user", "assistant"}:
        raise RuntimeError(f"Unexpected message role from database: {role}")
    return role
