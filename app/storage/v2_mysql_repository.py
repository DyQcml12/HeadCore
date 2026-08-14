from __future__ import annotations

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
    SessionRecord,
    new_uuid,
    utc_now,
)
from app.storage.mysql_repository import MySQLChatRepository, mysql_datetime
from app.storage.v2_models import (
    PlatformName,
    RelationshipType,
    V2ChatMessage,
    V2PendingRelationshipClaim,
    V2PersonaContext,
    V2PlatformAccount,
    V2Profile,
    V2RecentChat,
    V2RelationshipContext,
    account_from_row,
    build_relationship_context,
    chat_message_from_row,
    fallback_persona_context,
    normalize_platform_group_id,
    pending_claim_from_row,
    persona_context_from_row,
    profile_from_row,
    recent_chat_from_row,
)
from app.storage.v2_repository import DatabaseV2Repository


class MySQLDatabaseV2Repository(MySQLChatRepository, DatabaseV2Repository):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    async def find_relationship_context(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        platform_group_id: str | None = None,
    ) -> V2RelationshipContext | None:
        row = await self._fetch_profile_account_row(
            platform=platform,
            platform_user_id=platform_user_id.strip(),
            platform_group_id=normalize_platform_group_id(platform_group_id),
        )
        if row is None:
            return None
        return await self._context_from_row(row)

    async def get_control_status_snapshot(
        self,
        *,
        required_tables: tuple[str, ...],
    ) -> dict[str, Any]:
        inspected_tables = (*required_tables, "schema_migrations")
        placeholders = ", ".join("%s" for _table in inspected_tables)
        table_rows = await self._fetchall(
            f"""
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME IN ({placeholders})
            """,
            (self.settings.mysql_database, *inspected_tables),
        )
        existing_tables = {str(row["TABLE_NAME"]) for row in table_rows}
        schema_row = None
        if "schema_migrations" in existing_tables:
            schema_row = await self._fetchone(
                """
                SELECT version
                FROM schema_migrations
                WHERE version = %s
                LIMIT 1
                """,
                ("v2.001_hutao_chat_core_schema",),
            )
        admin_row = None
        if "admin_profile" in existing_tables:
            admin_row = await self._fetchone(
                """
                SELECT profile_id
                FROM admin_profile
                WHERE singleton_id = 1
                LIMIT 1
                """,
                (),
            )
        return {
            "schema_version": str(schema_row["version"]) if schema_row else "",
            "tables": existing_tables,
            "admin_exists": admin_row is not None,
        }

    async def get_admin_profile_snapshot(self) -> dict[str, Any] | None:
        profile = await self._fetchone(
            """
            SELECT p.*,
                   EXISTS(
                       SELECT 1 FROM admin_private_profile private
                       WHERE private.profile_id = p.id
                   ) AS private_profile_configured
            FROM admin_profile admin
            INNER JOIN profiles p ON p.id = admin.profile_id
            WHERE admin.singleton_id = 1
            LIMIT 1
            """,
            (),
        )
        if profile is None:
            return None
        accounts = await self._fetchall(
            """
            SELECT *
            FROM platform_accounts
            WHERE profile_id = %s
            ORDER BY is_primary DESC, created_at ASC
            """,
            (profile["id"],),
        )
        return {"profile": profile, "accounts": accounts}

    async def list_profile_snapshots(
        self,
        *,
        relationship_type: RelationshipType | None,
        verified: bool | None,
        platform: PlatformName | None,
        query: str,
        limit: int,
        cursor_updated_at: str | None,
        cursor_profile_id: str | None,
    ) -> list[dict[str, Any]]:
        conditions = ["p.status <> 'deleted'"]
        params: list[object] = []
        if relationship_type is not None:
            conditions.append("p.relationship_type = %s")
            params.append(relationship_type)
        if verified is not None:
            conditions.append("p.verified = %s")
            params.append(verified)
        if platform is not None:
            conditions.append(
                "EXISTS (SELECT 1 FROM platform_accounts fpa WHERE fpa.profile_id = p.id AND fpa.platform = %s)"
            )
            params.append(platform)
        if query:
            conditions.append(
                "(p.display_name LIKE %s OR EXISTS (SELECT 1 FROM platform_accounts qpa "
                "WHERE qpa.profile_id = p.id AND qpa.display_name LIKE %s))"
            )
            pattern = f"%{query}%"
            params.extend((pattern, pattern))
        if cursor_updated_at is not None and cursor_profile_id is not None:
            conditions.append("(p.updated_at < %s OR (p.updated_at = %s AND p.id < %s))")
            params.extend((cursor_updated_at, cursor_updated_at, cursor_profile_id))
        params.append(limit)
        return await self._fetchall(
            f"""
            SELECT p.*,
                   COUNT(DISTINCT pa.id) AS account_count,
                   MAX(pa.last_seen_at) AS last_seen_at,
                   GROUP_CONCAT(
                       DISTINCT CONCAT(sl.label_type, ':', sl.label_text)
                       ORDER BY sl.created_at DESC SEPARATOR '\\n'
                   ) AS labels_text
            FROM profiles p
            LEFT JOIN platform_accounts pa ON pa.profile_id = p.id
            LEFT JOIN profile_social_labels sl ON sl.profile_id = p.id
            WHERE {' AND '.join(conditions)}
            GROUP BY p.id
            ORDER BY p.updated_at DESC, p.id DESC
            LIMIT %s
            """,
            tuple(params),
        )

    async def get_profile_detail_snapshot(self, *, profile_id: str) -> dict[str, Any] | None:
        profile = await self._fetchone(
            """
            SELECT p.*,
                   COUNT(DISTINCT pa.id) AS account_count,
                   MAX(pa.last_seen_at) AS last_seen_at
            FROM profiles p
            LEFT JOIN platform_accounts pa ON pa.profile_id = p.id
            WHERE p.id = %s AND p.status <> 'deleted'
            GROUP BY p.id
            LIMIT 1
            """,
            (profile_id,),
        )
        if profile is None:
            return None
        accounts = await self._fetchall(
            "SELECT * FROM platform_accounts WHERE profile_id = %s ORDER BY is_primary DESC, created_at ASC",
            (profile_id,),
        )
        labels = await self._fetchall(
            """
            SELECT label_type, label_text, verified
            FROM profile_social_labels
            WHERE profile_id = %s
            ORDER BY created_at DESC
            """,
            (profile_id,),
        )
        portrait = await self._fetchone(
            """
            SELECT preferred_name, public_alias, communication_style,
                   known_context_summary, last_interaction_summary, updated_at
            FROM profile_portraits WHERE profile_id = %s LIMIT 1
            """,
            (profile_id,),
        )
        emotion = await self._fetchone(
            """
            SELECT recent_mood, support_need_level, conflict_level, warmth_level,
                   last_detected_at, decay_after, updated_at
            FROM profile_emotional_state WHERE profile_id = %s LIMIT 1
            """,
            (profile_id,),
        )
        conversations = await self._fetchall(
            """
            SELECT id, platform, conversation_type, title, updated_at AS last_message_at
            FROM conversations WHERE owner_profile_id = %s
            ORDER BY updated_at DESC LIMIT 10
            """,
            (profile_id,),
        )
        events = await self._fetchall(
            """
            SELECT id, event_type, reason, created_at
            FROM relationship_events WHERE profile_id = %s
            ORDER BY created_at DESC LIMIT 10
            """,
            (profile_id,),
        )
        memory_rows = await self._fetchall(
            """
            SELECT visibility_scope AS scope, COUNT(*) AS memory_count
            FROM memories WHERE profile_id = %s AND active = TRUE
            GROUP BY visibility_scope
            """,
            (profile_id,),
        )
        return {
            "profile": profile,
            "accounts": accounts,
            "labels": labels,
            "portrait": portrait,
            "emotion": emotion,
            "conversations": conversations,
            "events": events,
            "memory_counts": memory_rows,
        }

    async def update_profile_relationship(
        self,
        *,
        profile_id: str,
        relationship_type: RelationshipType,
        verified: bool,
        changed_by_profile_id: str,
        reason: str,
    ) -> dict[str, object]:
        profile = await self._fetchone(
            """
            SELECT id, relationship_type, verified, status
            FROM profiles WHERE id = %s LIMIT 1
            """,
            (profile_id,),
        )
        if profile is None or str(profile.get("status")) == "deleted":
            return {"status": "not_found", "profile_id": profile_id}
        admin = await self._fetchone(
            "SELECT profile_id FROM admin_profile WHERE singleton_id = 1 LIMIT 1",
            (),
        )
        if relationship_type == "admin_partner" and (
            admin is None or str(admin["profile_id"]) != profile_id
        ):
            return {"status": "admin_transfer_required", "profile_id": profile_id}
        old_relationship = str(profile["relationship_type"])
        old_verified = bool(profile.get("verified"))
        if old_relationship == relationship_type and old_verified == verified:
            return {
                "status": "unchanged",
                "profile_id": profile_id,
                "old_relationship_type": old_relationship,
                "new_relationship_type": relationship_type,
                "verified": verified,
            }
        timestamp = utc_now()
        await self._execute(
            """
            UPDATE profiles
            SET relationship_type = %s, verified = %s,
                trust_level = %s, affection_level = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                relationship_type,
                verified,
                default_trust_level(relationship_type),
                default_affection_level(relationship_type),
                mysql_datetime(timestamp),
                profile_id,
            ),
        )
        await self._record_relationship_event(
            profile_id=profile_id,
            event_type="set_role",
            old_value={"relationship_type": old_relationship, "verified": old_verified},
            new_value={"relationship_type": relationship_type, "verified": verified},
            changed_by_profile_id=changed_by_profile_id,
            reason=reason,
            timestamp=timestamp,
        )
        return {
            "status": "updated",
            "profile_id": profile_id,
            "old_relationship_type": old_relationship,
            "new_relationship_type": relationship_type,
            "verified": verified,
        }

    async def record_database_control_event(
        self,
        *,
        actor_profile_id: str | None,
        platform: str,
        command_name: str,
        status: str,
        reason_code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        if status not in {"accepted", "rejected", "failed"}:
            raise ValueError(f"Unsupported database control event status: {status}")
        await self._execute(
            """
            INSERT INTO platform_command_events (
                id, message_id, actor_profile_id, command_name, platform,
                target_platform_user_id, status, reason_code, details_json, created_at
            )
            VALUES (%s, NULL, %s, %s, %s, NULL, %s, %s, %s, %s)
            """,
            (
                new_uuid(),
                actor_profile_id,
                command_name,
                platform,
                status,
                reason_code,
                redact_secrets(json.dumps(details or {}, ensure_ascii=False)),
                mysql_datetime(utc_now()),
            ),
        )

    async def list_database_control_events(self, *, limit: int) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT id, command_name, platform, status, reason_code, created_at
            FROM platform_command_events
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (max(1, min(limit, 100)),),
        )

    async def ensure_default_personas(self) -> None:
        timestamp = utc_now()
        # Only the Hu Tao registry profile is deployable. Archive prior runtime
        # personas instead of deleting their audit history or foreign keys.
        await self._execute(
            """
            UPDATE personas
            SET status = 'archived',
                default_for_admin = FALSE,
                default_for_normal_friend = FALSE,
                updated_at = %s
            WHERE code <> 'hutao_v1' AND status = 'active'
            """,
            (mysql_datetime(timestamp),),
        )
        defaults = [
            {
                "id": "00000000-0000-0000-0000-000000000101",
                "code": "hutao_v1",
                "display_name": "胡桃",
                "description": "Projection of the active persona registry profile; behavior is defined outside the database.",
                "default_for_admin": True,
                "default_for_normal_friend": True,
                "version_id": "00000000-0000-0000-0000-000000000201",
                "version_label": "hutao_v1-registry",
                "prompt_template": "Use the persona registry profile hutao_v1; database rows must not define runtime prompt behavior.",
            },
        ]
        for persona in defaults:
            await self._execute(
                """
                INSERT INTO personas (
                    id, code, display_name, description, status,
                    default_for_admin, default_for_normal_friend,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    display_name = VALUES(display_name),
                    description = VALUES(description),
                    status = 'active',
                    default_for_admin = VALUES(default_for_admin),
                    default_for_normal_friend = VALUES(default_for_normal_friend),
                    updated_at = VALUES(updated_at)
                """,
                (
                    persona["id"],
                    persona["code"],
                    persona["display_name"],
                    persona["description"],
                    persona["default_for_admin"],
                    persona["default_for_normal_friend"],
                    mysql_datetime(timestamp),
                    mysql_datetime(timestamp),
                ),
            )
            await self._execute(
                """
                INSERT INTO persona_versions (
                    id, persona_id, version_label, prompt_template,
                    style_rules_json, safety_rules_json, memory_policy_json,
                    active, created_by_profile_id, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NULL, %s)
                ON DUPLICATE KEY UPDATE
                    prompt_template = VALUES(prompt_template),
                    style_rules_json = VALUES(style_rules_json),
                    safety_rules_json = VALUES(safety_rules_json),
                    memory_policy_json = VALUES(memory_policy_json),
                    active = TRUE
                """,
                (
                    persona["version_id"],
                    persona["id"],
                    persona["version_label"],
                    persona["prompt_template"],
                    "{}",
                    "{}",
                    "{}",
                    mysql_datetime(timestamp),
                ),
            )

    async def resolve_persona_context(
        self,
        *,
        relationship_context: V2RelationshipContext,
        conversation_id: str | None = None,
        platform_thread_id: str | None = None,
    ) -> V2PersonaContext:
        if conversation_id:
            row = await self._fetch_conversation_persona_row(conversation_id=conversation_id)
            if _is_hutao_persona_row(row):
                return persona_context_from_row(row, source_scope="conversation")

        row = await self._fetch_bound_persona_row(
            relationship_context=relationship_context,
            platform_thread_id=platform_thread_id,
        )
        if _is_hutao_persona_row(row):
            scope = str(row.get("binding_scope") or "global")
            if scope not in {"global", "relationship_type", "profile", "platform", "conversation"}:
                scope = "global"
            return persona_context_from_row(row, source_scope=scope)  # type: ignore[arg-type]

        row = await self._fetch_default_persona_row(
            relationship_type=relationship_context.effective_relationship_type,
        )
        if _is_hutao_persona_row(row):
            return persona_context_from_row(row, source_scope="relationship_type")
        return fallback_persona_context(relationship_context.effective_relationship_type)

    async def ensure_session(self, *, user_id: str, client_session_id: str) -> SessionRecord:
        chat_identity = infer_chat_identity(user_id=user_id, client_session_id=client_session_id)
        existing = await self._fetchone(
            """
            SELECT id, owner_profile_id, created_at, updated_at
            FROM conversations
            WHERE platform = %s
              AND conversation_type = %s
              AND platform_thread_id = %s
            LIMIT 1
            """,
            (
                chat_identity["platform"],
                chat_identity["conversation_type"],
                client_session_id,
            ),
        )
        if existing is not None:
            return SessionRecord(
                id=str(existing["id"]),
                user_id=user_id,
                client_session_id=client_session_id,
                created_at=str(existing["created_at"]),
                updated_at=str(existing["updated_at"]),
            )

        profile_id = None
        if chat_identity["platform"] == "core":
            profile_id = await self._active_core_profile_id(user_id=user_id)
            if profile_id is None:
                raise RuntimeError("Database V2 core chats require an active profile")
        elif chat_identity["platform"] in {"qq", "wechat"} and chat_identity["platform_user_id"]:
            context = await self.resolve_relationship_context(
                platform=chat_identity["platform"],  # type: ignore[arg-type]
                platform_user_id=str(chat_identity["platform_user_id"]),
                platform_group_id=str(chat_identity["platform_group_id"] or ""),
            )
            profile_id = context.profile.id

        timestamp = utc_now()
        conversation_id = new_uuid()
        await self._execute(
            """
            INSERT INTO conversations (
                id, platform, conversation_type, platform_thread_id,
                owner_profile_id, title, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                conversation_id,
                chat_identity["platform"],
                chat_identity["conversation_type"],
                client_session_id,
                profile_id,
                client_session_id,
                mysql_datetime(timestamp),
                mysql_datetime(timestamp),
            ),
        )
        return SessionRecord(
            id=conversation_id,
            user_id=user_id,
            client_session_id=client_session_id,
            created_at=timestamp,
            updated_at=timestamp,
        )

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
        timestamp = utc_now()
        conversation = await self._fetch_conversation(conversation_id=session_id)
        profile_id = str(conversation["owner_profile_id"]) if conversation and conversation.get("owner_profile_id") else None
        platform = str(conversation["platform"]) if conversation else infer_chat_identity(user_id=user_id, client_session_id=session_id)["platform"]
        account_id = await self._find_platform_account_id(
            profile_id=profile_id,
            platform=platform,
            user_id=user_id,
        )
        record = MessageRecord(
            id=new_uuid(),
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=safe_content,
            content_hash=text_hash(safe_content),
            model_invocation_id=model_invocation_id,
            created_at=timestamp,
        )
        await self._execute(
            """
            INSERT INTO messages (
                id, conversation_id, profile_id, platform_account_id, platform,
                platform_message_id, direction, role, content_type, content,
                content_hash, reply_to_message_id, model_invocation_id,
                safety_status, memory_eligible, visible_to_admin, created_at
            )
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, 'text', %s, %s, NULL, %s,
                    'not_checked', %s, TRUE, %s)
            """,
            (
                record.id,
                record.session_id,
                profile_id,
                account_id,
                normalize_message_platform(platform),
                "inbound" if role == "user" else "outbound",
                role,
                record.content,
                record.content_hash,
                record.model_invocation_id,
                role == "user",
                mysql_datetime(record.created_at),
            ),
        )
        await self._touch_conversation(conversation_id=session_id, timestamp=timestamp)
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
        timestamp = utc_now()
        conversation = await self._fetch_conversation(conversation_id=session_id)
        profile_id = str(conversation["owner_profile_id"]) if conversation and conversation.get("owner_profile_id") else None
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
            created_at=timestamp,
        )
        await self._execute(
            """
            INSERT INTO model_invocations (
                id, conversation_id, profile_id, provider, model, used_live_api,
                fallback_used, latency_ms, prompt_hash, response_hash, error,
                request_metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.id,
                record.session_id,
                profile_id,
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
        timestamp = utc_now()
        record = PersonaEvaluationRecord(
            id=new_uuid(),
            message_id=message_id,
            model_invocation_id=model_invocation_id,
            passed=passed,
            score=score,
            evaluator_provider=evaluator_provider,
            evaluator_model=evaluator_model,
            reasons_json=reasons_json,
            created_at=timestamp,
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
        profile_id = await self._profile_id_for_chat_user(user_id=user_id, session_id=session_id)
        if profile_id is None:
            raise RuntimeError("Database V2 memory writes require a resolved platform profile")
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
                id, profile_id, memory_type, content, content_hash,
                source_message_id, confidence, active, expires_at, deleted_at,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NULL, NULL, %s, %s)
            """,
            (
                record.id,
                profile_id,
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
        profile_id = await self._profile_id_for_chat_user(user_id=user_id, session_id=None)
        if profile_id is None:
            return []
        params: list[Any] = [profile_id]
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
            SELECT id, memory_type, content, content_hash, source_message_id,
                   confidence, created_at, updated_at
            FROM memories
            WHERE profile_id = %s
              AND active = TRUE
              AND deleted_at IS NULL{type_clause}
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return [
            MemoryRecord(
                id=str(row["id"]),
                user_id=user_id,
                session_id=None,
                memory_type=str(row["memory_type"]),
                content=str(row["content"]),
                content_hash=str(row["content_hash"]),
                source_message_id=(
                    str(row["source_message_id"]) if row.get("source_message_id") is not None else None
                ),
                confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in reversed(rows)
        ]

    async def delete_memory(self, *, user_id: str, memory_id: str) -> bool:
        profile_id = await self._profile_id_for_chat_user(user_id=user_id, session_id=None)
        if profile_id is None:
            return False
        affected_rows = await self._execute(
            """
            UPDATE memories
            SET active = FALSE, deleted_at = %s, updated_at = %s
            WHERE id = %s AND profile_id = %s
            """,
            (
                mysql_datetime(utc_now()),
                mysql_datetime(utc_now()),
                memory_id,
                profile_id,
            ),
        )
        return affected_rows > 0

    async def list_recent_messages(self, *, session_id: str, limit: int = 8) -> list[MessageRecord]:
        rows = await self._fetchall(
            """
            SELECT id, conversation_id, profile_id, role, content, content_hash,
                   model_invocation_id, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        return [legacy_message_from_v2_row(row) for row in reversed(rows)]

    async def list_recent_messages_by_user(self, *, user_id: str, limit: int = 12) -> list[MessageRecord]:
        profile_id = await self._profile_id_for_chat_user(user_id=user_id, session_id=None)
        if profile_id is None:
            return []
        rows = await self._fetchall(
            """
            SELECT id, conversation_id, profile_id, role, content, content_hash,
                   model_invocation_id, created_at
            FROM messages
            WHERE profile_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (profile_id, limit),
        )
        return [legacy_message_from_v2_row(row) for row in reversed(rows)]

    async def list_recent_user_ids(self, *, limit: int = 20) -> list[str]:
        rows = await self._fetchall(
            """
            SELECT p.platform, p.platform_user_id, MAX(m.created_at) AS last_message_at
            FROM messages m
            INNER JOIN platform_accounts p ON p.profile_id = m.profile_id
            WHERE m.profile_id IS NOT NULL
              AND p.is_primary = TRUE
            GROUP BY p.platform, p.platform_user_id
            ORDER BY last_message_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [f"{row['platform']}-{row['platform_user_id']}" for row in rows]

    async def resolve_contact(
        self,
        *,
        platform: str,
        platform_user_id: str,
        platform_group_id: str | None = None,
        display_name: str = "",
        owner_platform_user_ids: set[str] | None = None,
    ) -> ContactRecord:
        if platform not in {"qq", "wechat"}:
            raise ValueError(f"Unsupported V2 contact platform: {platform}")
        context = await self.resolve_relationship_context(
            platform=platform,  # type: ignore[arg-type]
            platform_user_id=platform_user_id,
            platform_group_id=platform_group_id,
            display_name=display_name,
        )
        return legacy_contact_from_v2_context(context)

    async def import_legacy_jsonl_snapshot(
        self,
        *,
        snapshot: dict[str, list[dict[str, Any]]],
    ) -> dict[str, int]:
        stats = {
            "profiles": 0,
            "platform_accounts": 0,
            "conversations": 0,
            "messages": 0,
            "model_invocations": 0,
            "persona_evaluations": 0,
            "memories": 0,
            "skipped_memories_without_profile": 0,
        }
        profile_by_contact_id: dict[str, str] = {}
        profile_by_user_id: dict[str, str] = {}

        for contact in snapshot.get("contacts", []):
            profile_id = str(contact.get("id") or new_uuid())
            relationship_type = legacy_role_to_v2_relationship(str(contact.get("relationship_role") or ""))
            timestamp = str(contact.get("created_at") or utc_now())
            await self._execute(
                """
                INSERT INTO profiles (
                    id, display_name, relationship_type, verified, trust_level,
                    affection_level, notes, status, merged_into_profile_id,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', NULL, %s, %s)
                ON DUPLICATE KEY UPDATE
                    display_name = VALUES(display_name),
                    relationship_type = VALUES(relationship_type),
                    verified = VALUES(verified),
                    trust_level = VALUES(trust_level),
                    affection_level = VALUES(affection_level),
                    notes = VALUES(notes),
                    updated_at = VALUES(updated_at)
                """,
                (
                    profile_id,
                    str(contact.get("display_name") or profile_id),
                    relationship_type,
                    relationship_type == "admin_partner",
                    int(contact.get("trust_level") or default_trust_level(relationship_type)),
                    int(contact.get("affection_level") or default_affection_level(relationship_type)),
                    str(contact.get("notes") or "migrated from legacy storage"),
                    mysql_datetime(timestamp),
                    mysql_datetime(str(contact.get("updated_at") or timestamp)),
                ),
            )
            profile_by_contact_id[profile_id] = profile_id
            stats["profiles"] += 1

        for identity in snapshot.get("platform_identities", []):
            platform = str(identity.get("platform") or "").strip().lower()
            if platform not in {"qq", "wechat"}:
                continue
            platform_user_id = str(identity.get("platform_user_id") or "").strip()
            if not platform_user_id:
                continue
            contact_id = str(identity.get("contact_id") or "")
            profile_id = profile_by_contact_id.get(contact_id)
            if profile_id is None:
                context = await self.resolve_relationship_context(
                    platform=platform,  # type: ignore[arg-type]
                    platform_user_id=platform_user_id,
                    platform_group_id=str(identity.get("platform_group_id") or ""),
                )
                profile_id = context.profile.id
            account_id = str(identity.get("id") or new_uuid())
            timestamp = str(identity.get("created_at") or utc_now())
            await self._execute(
                """
                INSERT INTO platform_accounts (
                    id, profile_id, platform, platform_user_id, platform_group_id,
                    display_name, account_label, is_primary, status, confidence,
                    verified_by_profile_id, last_seen_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'unknown', TRUE, 'active', 70,
                        NULL, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    profile_id = VALUES(profile_id),
                    display_name = VALUES(display_name),
                    updated_at = VALUES(updated_at)
                """,
                (
                    account_id,
                    profile_id,
                    platform,
                    platform_user_id,
                    normalize_platform_group_id(str(identity.get("platform_group_id") or "")),
                    platform_user_id,
                    mysql_datetime(timestamp),
                    mysql_datetime(timestamp),
                    mysql_datetime(str(identity.get("updated_at") or timestamp)),
                ),
            )
            profile_by_user_id[f"{platform}-{platform_user_id}"] = profile_id
            stats["platform_accounts"] += 1

        for session in snapshot.get("sessions", []):
            user_id = str(session.get("user_id") or "")
            client_session_id = str(session.get("client_session_id") or session.get("id") or "")
            chat_identity = infer_chat_identity(user_id=user_id, client_session_id=client_session_id)
            profile_id = await self._profile_id_for_legacy_user(
                user_id=user_id,
                profile_by_user_id=profile_by_user_id,
                chat_identity=chat_identity,
            )
            timestamp = str(session.get("created_at") or utc_now())
            await self._execute(
                """
                INSERT INTO conversations (
                    id, platform, conversation_type, platform_thread_id,
                    owner_profile_id, title, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    owner_profile_id = VALUES(owner_profile_id),
                    title = VALUES(title),
                    updated_at = VALUES(updated_at)
                """,
                (
                    str(session.get("id") or new_uuid()),
                    chat_identity["platform"],
                    chat_identity["conversation_type"],
                    client_session_id,
                    profile_id,
                    client_session_id,
                    mysql_datetime(timestamp),
                    mysql_datetime(str(session.get("updated_at") or timestamp)),
                ),
            )
            stats["conversations"] += 1

        for invocation in snapshot.get("model_invocations", []):
            user_id = str(invocation.get("user_id") or "")
            profile_id = profile_by_user_id.get(user_id)
            created_at = str(invocation.get("created_at") or utc_now())
            await self._execute(
                """
                INSERT INTO model_invocations (
                    id, conversation_id, profile_id, provider, model, used_live_api,
                    fallback_used, latency_ms, prompt_hash, response_hash, error,
                    request_metadata_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE error = VALUES(error)
                """,
                (
                    str(invocation.get("id") or new_uuid()),
                    str(invocation.get("session_id") or ""),
                    profile_id,
                    str(invocation.get("provider") or ""),
                    str(invocation.get("model") or ""),
                    bool(invocation.get("used_live_api")),
                    bool(invocation.get("fallback_used")),
                    float(invocation.get("latency_ms") or 0),
                    str(invocation.get("prompt_hash") or ""),
                    str(invocation.get("response_hash") or ""),
                    redact_secrets(str(invocation.get("error"))) if invocation.get("error") else None,
                    json.dumps(invocation.get("request_metadata_json") or {}, ensure_ascii=False),
                    mysql_datetime(created_at),
                ),
            )
            stats["model_invocations"] += 1

        for message in snapshot.get("messages", []):
            user_id = str(message.get("user_id") or "")
            chat_identity = infer_chat_identity(
                user_id=user_id,
                client_session_id=str(message.get("session_id") or ""),
            )
            profile_id = profile_by_user_id.get(user_id)
            created_at = str(message.get("created_at") or utc_now())
            role = str(message.get("role") or "user")
            if role not in {"user", "assistant"}:
                role = "user"
            await self._execute(
                """
                INSERT INTO messages (
                    id, conversation_id, profile_id, platform_account_id, platform,
                    platform_message_id, direction, role, content_type, content,
                    content_hash, reply_to_message_id, model_invocation_id,
                    safety_status, memory_eligible, visible_to_admin, created_at
                )
                VALUES (%s, %s, %s, NULL, %s, NULL, %s, %s, 'text', %s, %s, NULL, %s,
                        'not_checked', %s, TRUE, %s)
                ON DUPLICATE KEY UPDATE content_hash = VALUES(content_hash)
                """,
                (
                    str(message.get("id") or new_uuid()),
                    str(message.get("session_id") or ""),
                    profile_id,
                    normalize_message_platform(str(chat_identity["platform"])),
                    "inbound" if role == "user" else "outbound",
                    role,
                    redact_secrets(str(message.get("content") or "")),
                    str(message.get("content_hash") or text_hash(str(message.get("content") or ""))),
                    message.get("model_invocation_id"),
                    role == "user",
                    mysql_datetime(created_at),
                ),
            )
            stats["messages"] += 1

        for evaluation in snapshot.get("persona_evaluations", []):
            created_at = str(evaluation.get("created_at") or utc_now())
            await self._execute(
                """
                INSERT INTO persona_evaluations (
                    id, message_id, model_invocation_id, passed, score,
                    evaluator_provider, evaluator_model, reasons_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE reasons_json = VALUES(reasons_json)
                """,
                (
                    str(evaluation.get("id") or new_uuid()),
                    str(evaluation.get("message_id") or ""),
                    evaluation.get("model_invocation_id"),
                    bool(evaluation.get("passed")),
                    evaluation.get("score"),
                    str(evaluation.get("evaluator_provider") or ""),
                    str(evaluation.get("evaluator_model") or ""),
                    json.dumps(evaluation.get("reasons_json") or {}, ensure_ascii=False),
                    mysql_datetime(created_at),
                ),
            )
            stats["persona_evaluations"] += 1

        for memory in snapshot.get("memories", []):
            user_id = str(memory.get("user_id") or "")
            profile_id = profile_by_user_id.get(user_id)
            if profile_id is None:
                stats["skipped_memories_without_profile"] += 1
                continue
            created_at = str(memory.get("created_at") or utc_now())
            updated_at = str(memory.get("updated_at") or created_at)
            await self._execute(
                """
                INSERT INTO memories (
                    id, profile_id, memory_type, content, content_hash,
                    source_message_id, confidence, active, expires_at, deleted_at,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, NULL, NULL, %s, %s)
                ON DUPLICATE KEY UPDATE
                    content = VALUES(content),
                    content_hash = VALUES(content_hash),
                    updated_at = VALUES(updated_at)
                """,
                (
                    str(memory.get("id") or new_uuid()),
                    profile_id,
                    str(memory.get("memory_type") or ""),
                    redact_secrets(str(memory.get("content") or "")),
                    str(memory.get("content_hash") or text_hash(str(memory.get("content") or ""))),
                    memory.get("source_message_id"),
                    memory.get("confidence"),
                    mysql_datetime(created_at),
                    mysql_datetime(updated_at),
                ),
            )
            stats["memories"] += 1
        return stats

    async def _profile_id_for_legacy_user(
        self,
        *,
        user_id: str,
        profile_by_user_id: dict[str, str],
        chat_identity: dict[str, object],
    ) -> str | None:
        if user_id in profile_by_user_id:
            return profile_by_user_id[user_id]
        if chat_identity["platform"] not in {"qq", "wechat"} or not chat_identity["platform_user_id"]:
            return None
        context = await self.resolve_relationship_context(
            platform=chat_identity["platform"],  # type: ignore[arg-type]
            platform_user_id=str(chat_identity["platform_user_id"]),
            platform_group_id=str(chat_identity["platform_group_id"] or ""),
        )
        profile_by_user_id[user_id] = context.profile.id
        return context.profile.id

    async def bootstrap_admin_if_missing(
        self,
        *,
        qq_ids: list[str],
        wechat_ids: list[str],
        display_name: str,
    ) -> str | None:
        existing = await self._fetchone(
            """
            SELECT profile_id
            FROM admin_profile
            WHERE singleton_id = 1
            LIMIT 1
            """,
            (),
        )
        if existing is not None:
            return None

        timestamp = utc_now()
        profile_id = new_uuid()
        name = display_name.strip() or "admin"
        await self._execute(
            """
            INSERT INTO profiles (
                id, display_name, relationship_type, verified, trust_level,
                affection_level, notes, status, merged_into_profile_id,
                created_at, updated_at
            )
            VALUES (%s, %s, 'admin_partner', TRUE, 100, 100, %s, 'active', NULL, %s, %s)
            """,
            (
                profile_id,
                name,
                "bootstrap admin profile",
                mysql_datetime(timestamp),
                mysql_datetime(timestamp),
            ),
        )
        await self._execute(
            """
            INSERT INTO admin_profile (singleton_id, profile_id, created_at, updated_at)
            VALUES (1, %s, %s, %s)
            """,
            (profile_id, mysql_datetime(timestamp), mysql_datetime(timestamp)),
        )

        for index, qq_id in enumerate(clean_ids(qq_ids)):
            await self._insert_platform_account(
                profile_id=profile_id,
                platform="qq",
                platform_user_id=qq_id,
                platform_group_id="",
                display_name=name,
                account_label="main" if index == 0 else "alt",
                is_primary=index == 0,
                status="active",
                confidence=100,
                verified_by_profile_id=profile_id,
                timestamp=timestamp,
            )
        for index, wechat_id in enumerate(clean_ids(wechat_ids)):
            await self._insert_platform_account(
                profile_id=profile_id,
                platform="wechat",
                platform_user_id=wechat_id,
                platform_group_id="",
                display_name=name,
                account_label="main" if index == 0 else "alt",
                is_primary=index == 0,
                status="active",
                confidence=100,
                verified_by_profile_id=profile_id,
                timestamp=timestamp,
            )
        await self._record_relationship_event(
            profile_id=profile_id,
            event_type="create",
            new_value={
                "relationship_type": "admin_partner",
                "bootstrap_qq_count": len(clean_ids(qq_ids)),
                "bootstrap_wechat_count": len(clean_ids(wechat_ids)),
            },
            changed_by_profile_id=profile_id,
            reason="bootstrap admin profile",
            timestamp=timestamp,
        )
        return profile_id

    async def resolve_relationship_context(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        platform_group_id: str | None = None,
        display_name: str = "",
    ) -> V2RelationshipContext:
        normalized_user_id = platform_user_id.strip()
        normalized_group_id = normalize_platform_group_id(platform_group_id)
        row = await self._fetch_profile_account_row(
            platform=platform,
            platform_user_id=normalized_user_id,
            platform_group_id=normalized_group_id,
        )
        if row is None:
            timestamp = utc_now()
            profile_id = new_uuid()
            local_name = display_name.strip() or normalized_user_id
            await self._execute(
                """
                INSERT INTO profiles (
                    id, display_name, relationship_type, verified, trust_level,
                    affection_level, notes, status, merged_into_profile_id,
                    created_at, updated_at
                )
                VALUES (%s, %s, 'normal_friend', FALSE, 10, 10, %s, 'active', NULL, %s, %s)
                """,
                (
                    profile_id,
                    local_name,
                    "auto-created from platform account",
                    mysql_datetime(timestamp),
                    mysql_datetime(timestamp),
                ),
            )
            account_id = await self._insert_platform_account(
                profile_id=profile_id,
                platform=platform,
                platform_user_id=normalized_user_id,
                platform_group_id=normalized_group_id,
                display_name=local_name,
                account_label="unknown",
                is_primary=True,
                status="active",
                confidence=50,
                verified_by_profile_id=None,
                timestamp=timestamp,
            )
            await self._record_relationship_event(
                profile_id=profile_id,
                platform=platform,
                platform_user_id=normalized_user_id,
                event_type="create",
                new_value={
                    "relationship_type": "normal_friend",
                    "verified": False,
                    "platform_account_id": account_id,
                },
                reason="auto-created unknown platform account",
                timestamp=timestamp,
            )
            row = await self._fetch_profile_account_row(
                platform=platform,
                platform_user_id=normalized_user_id,
                platform_group_id=normalized_group_id,
            )
            if row is None:
                raise RuntimeError("Failed to reload V2 profile/account after creation")
        else:
            await self._execute(
                """
                UPDATE platform_accounts
                SET display_name = %s, last_seen_at = %s, updated_at = %s
                WHERE id = %s
                """,
                (
                    display_name.strip() or str(row.get("account_display_name") or ""),
                    mysql_datetime(utc_now()),
                    mysql_datetime(utc_now()),
                    row["account_id"],
                ),
            )
        return await self._context_from_row(row)

    async def set_relationship(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        relationship_type: RelationshipType,
        display_name: str = "",
        changed_by_profile_id: str | None = None,
        reason: str = "",
    ) -> V2RelationshipContext:
        context = await self.resolve_relationship_context(
            platform=platform,
            platform_user_id=platform_user_id,
            display_name=display_name,
        )
        timestamp = utc_now()
        old_value = {
            "relationship_type": context.profile.relationship_type,
            "verified": context.profile.verified,
        }
        verified = relationship_type == "admin_partner" or context.profile.verified
        await self._execute(
            """
            UPDATE profiles
            SET relationship_type = %s, verified = %s, display_name = %s,
                trust_level = %s, affection_level = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                relationship_type,
                verified,
                display_name.strip() or context.profile.display_name,
                default_trust_level(relationship_type),
                default_affection_level(relationship_type),
                mysql_datetime(timestamp),
                context.profile.id,
            ),
        )
        await self._record_relationship_event(
            profile_id=context.profile.id,
            platform=platform,
            platform_user_id=platform_user_id.strip(),
            event_type="set_role",
            old_value=old_value,
            new_value={
                "relationship_type": relationship_type,
                "verified": verified,
            },
            changed_by_profile_id=changed_by_profile_id,
            reason=reason,
            timestamp=timestamp,
        )
        return await self.resolve_relationship_context(
            platform=platform,
            platform_user_id=platform_user_id,
            display_name=display_name,
        )

    async def bind_accounts(
        self,
        *,
        source_platform: PlatformName,
        source_platform_user_id: str,
        target_platform: PlatformName,
        target_platform_user_id: str,
        changed_by_profile_id: str,
        reason: str = "",
    ) -> str:
        source = await self.resolve_relationship_context(
            platform=source_platform,
            platform_user_id=source_platform_user_id,
        )
        target = await self.resolve_relationship_context(
            platform=target_platform,
            platform_user_id=target_platform_user_id,
        )
        if source.profile.id == target.profile.id:
            return source.profile.id

        timestamp = utc_now()
        target_profile_id = source.profile.id
        old_profile_id = target.profile.id
        statements: list[tuple[str, tuple[Any, ...]]] = [
            (
                """
                UPDATE platform_accounts
                SET profile_id = %s, updated_at = %s
                WHERE profile_id = %s
                """,
                (target_profile_id, mysql_datetime(timestamp), old_profile_id),
            )
        ]
        for table_name in [
            "model_invocations",
            "messages",
            "safety_guard_events",
            "memories",
            "memory_events",
            "profile_social_labels",
            "relationship_events",
        ]:
            statements.append(
                (
                    f"""
                    UPDATE {table_name}
                    SET profile_id = %s
                    WHERE profile_id = %s
                    """,
                    (target_profile_id, old_profile_id),
                )
            )
        statements.append(
            (
                """
                UPDATE conversations
                SET owner_profile_id = %s, updated_at = %s
                WHERE owner_profile_id = %s
                """,
                (target_profile_id, mysql_datetime(timestamp), old_profile_id),
            )
        )
        statements.append(
            (
                """
                UPDATE platform_command_events
                SET actor_profile_id = %s
                WHERE actor_profile_id = %s
                """,
                (target_profile_id, old_profile_id),
            )
        )
        for table_name in ["profile_portraits", "profile_emotional_state"]:
            statements.append(
                (
                    f"""
                    UPDATE {table_name}
                    SET profile_id = %s
                    WHERE profile_id = %s
                      AND NOT EXISTS (
                          SELECT 1
                          FROM (SELECT profile_id FROM {table_name} WHERE profile_id = %s) AS existing_target
                      )
                    """,
                    (target_profile_id, old_profile_id, target_profile_id),
                )
            )
            statements.append(
                (
                    f"""
                    DELETE FROM {table_name}
                    WHERE profile_id = %s
                    """,
                    (old_profile_id,),
                )
            )
        statements.append(
            (
                """
                UPDATE profiles
                SET status = 'merged', merged_into_profile_id = %s, updated_at = %s
                WHERE id = %s
                """,
                (target_profile_id, mysql_datetime(timestamp), old_profile_id),
            )
        )
        statements.append(
            (
                """
                INSERT INTO relationship_events (
                    id, profile_id, platform, platform_user_id, event_type,
                    old_value, new_value, changed_by_profile_id, reason, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    new_uuid(),
                    target_profile_id,
                    target_platform,
                    target_platform_user_id,
                    "merge",
                    json.dumps({"merged_profile_id": old_profile_id}, ensure_ascii=False),
                    json.dumps({"target_profile_id": target_profile_id}, ensure_ascii=False),
                    changed_by_profile_id,
                    redact_secrets(reason or "bind platform accounts"),
                    mysql_datetime(timestamp),
                ),
            )
        )
        await self._execute_transaction(statements)
        return target_profile_id

    async def _execute_transaction(
        self, statements: list[tuple[str, tuple[Any, ...]]]
    ) -> None:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            for sql, params in statements:
                await cursor.execute(sql, params)
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            close_result = cursor.close()
            if inspect.isawaitable(close_result):
                await close_result
            connection.close()

    async def list_recent_chats(self, *, limit: int = 10) -> list[V2RecentChat]:
        rows = await self._fetchall(
            """
            SELECT
                c.id AS conversation_id,
                c.platform,
                c.conversation_type,
                c.platform_thread_id,
                c.title,
                c.owner_profile_id,
                p.display_name AS owner_display_name,
                p.relationship_type AS owner_relationship_type,
                MAX(m.created_at) AS last_message_at,
                COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN profiles p ON p.id = c.owner_profile_id
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.platform IN ('qq', 'wechat')
            GROUP BY
                c.id,
                c.platform,
                c.conversation_type,
                c.platform_thread_id,
                c.title,
                c.owner_profile_id,
                p.display_name,
                p.relationship_type,
                c.updated_at
            ORDER BY COALESCE(MAX(m.created_at), c.updated_at) DESC
            LIMIT %s
            """,
            (bounded_limit(limit, default=10, maximum=50),),
        )
        return [recent_chat_from_row(row) for row in rows]

    async def list_chat_history(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        limit: int = 20,
    ) -> list[V2ChatMessage]:
        row = await self._fetch_profile_account_row(
            platform=platform,
            platform_user_id=platform_user_id.strip(),
            platform_group_id="",
        )
        if row is None:
            return []

        rows = await self._fetchall(
            """
            SELECT
                m.id,
                m.conversation_id,
                m.profile_id,
                m.platform_account_id,
                m.platform,
                m.platform_message_id,
                m.direction,
                m.role,
                m.content_type,
                m.content,
                m.safety_status,
                m.memory_eligible,
                m.visible_to_admin,
                m.created_at,
                c.title AS conversation_title
            FROM messages m
            INNER JOIN conversations c ON c.id = m.conversation_id
            WHERE m.visible_to_admin = TRUE
              AND (
                  m.profile_id = %s
                  OR m.platform_account_id = %s
                  OR c.owner_profile_id = %s
              )
            ORDER BY m.created_at DESC
            LIMIT %s
            """,
            (
                row["profile_id"],
                row["account_id"],
                row["profile_id"],
                bounded_limit(limit, default=20, maximum=100),
            ),
        )
        return [chat_message_from_row(message_row) for message_row in rows]

    async def list_pending_relationship_claims(
        self,
        *,
        limit: int = 20,
    ) -> list[V2PendingRelationshipClaim]:
        rows = await self._fetchall(
            """
            SELECT
                id,
                platform,
                platform_user_id,
                claimed_name,
                claimed_relation_text,
                status,
                reviewed_by_profile_id,
                created_at,
                reviewed_at
            FROM relationship_pending_claims
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (bounded_limit(limit, default=20, maximum=100),),
        )
        return [pending_claim_from_row(row) for row in rows]

    async def approve_relationship_claim(
        self,
        *,
        claim_id: str,
        reviewed_by_profile_id: str,
    ) -> dict[str, object]:
        claim = await self._fetch_relationship_claim(claim_id=claim_id)
        if claim is None:
            return {"status": "not_found", "claim_id": claim_id}
        if claim.status != "pending":
            return {"status": "already_reviewed", "claim_id": claim.id, "claim_status": claim.status}

        timestamp = utc_now()
        context = await self.resolve_relationship_context(
            platform=claim.platform,
            platform_user_id=claim.platform_user_id,
            display_name=claim.claimed_name,
        )
        await self._execute(
            """
            UPDATE profiles
            SET verified = TRUE, trust_level = GREATEST(trust_level, 25), updated_at = %s
            WHERE id = %s
            """,
            (mysql_datetime(timestamp), context.profile.id),
        )
        await self._execute(
            """
            UPDATE platform_accounts
            SET confidence = GREATEST(confidence, 90),
                verified_by_profile_id = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (
                reviewed_by_profile_id,
                mysql_datetime(timestamp),
                context.platform_account.id,
            ),
        )
        await self._execute(
            """
            INSERT INTO profile_social_labels (
                id, profile_id, label_type, label_text, verified,
                verified_by_profile_id, source, created_at, updated_at
            )
            VALUES (%s, %s, 'user_claim', %s, TRUE, %s, 'user_claim', %s, %s)
            """,
            (
                new_uuid(),
                context.profile.id,
                claim.claimed_relation_text,
                reviewed_by_profile_id,
                mysql_datetime(timestamp),
                mysql_datetime(timestamp),
            ),
        )
        await self._execute(
            """
            UPDATE relationship_pending_claims
            SET status = 'approved', reviewed_by_profile_id = %s, reviewed_at = %s
            WHERE id = %s
            """,
            (reviewed_by_profile_id, mysql_datetime(timestamp), claim.id),
        )
        await self._record_relationship_event(
            profile_id=context.profile.id,
            platform=claim.platform,
            platform_user_id=claim.platform_user_id,
            event_type="verify",
            new_value={
                "claim_id": claim.id,
                "claimed_name": claim.claimed_name,
                "claimed_relation_text": claim.claimed_relation_text,
                "relationship_type": context.profile.relationship_type,
            },
            changed_by_profile_id=reviewed_by_profile_id,
            reason="admin approved relationship claim",
            timestamp=timestamp,
        )
        return {
            "status": "approved",
            "claim_id": claim.id,
            "profile_id": context.profile.id,
            "relationship_type": context.profile.relationship_type,
        }

    async def reject_relationship_claim(
        self,
        *,
        claim_id: str,
        reviewed_by_profile_id: str,
    ) -> dict[str, object]:
        claim = await self._fetch_relationship_claim(claim_id=claim_id)
        if claim is None:
            return {"status": "not_found", "claim_id": claim_id}
        if claim.status != "pending":
            return {"status": "already_reviewed", "claim_id": claim.id, "claim_status": claim.status}

        timestamp = utc_now()
        await self._execute(
            """
            UPDATE relationship_pending_claims
            SET status = 'rejected', reviewed_by_profile_id = %s, reviewed_at = %s
            WHERE id = %s
            """,
            (reviewed_by_profile_id, mysql_datetime(timestamp), claim.id),
        )
        row = await self._fetch_profile_account_row(
            platform=claim.platform,
            platform_user_id=claim.platform_user_id,
            platform_group_id="",
        )
        if row is not None:
            await self._record_relationship_event(
                profile_id=str(row["profile_id"]),
                platform=claim.platform,
                platform_user_id=claim.platform_user_id,
                event_type="unverify",
                new_value={
                    "claim_id": claim.id,
                    "claimed_name": claim.claimed_name,
                    "claimed_relation_text": claim.claimed_relation_text,
                },
                changed_by_profile_id=reviewed_by_profile_id,
                reason="admin rejected relationship claim",
                timestamp=timestamp,
            )
        return {"status": "rejected", "claim_id": claim.id}

    async def record_platform_command_event(
        self,
        *,
        message_id: str | None,
        actor_profile_id: str | None,
        command_name: str,
        platform: PlatformName,
        target_platform_user_id: str | None,
        status: str,
        reason_code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        if status not in {"accepted", "rejected", "failed"}:
            raise ValueError(f"Unsupported platform command status: {status}")
        await self._execute(
            """
            INSERT INTO platform_command_events (
                id, message_id, actor_profile_id, command_name, platform,
                target_platform_user_id, status, reason_code, details_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                new_uuid(),
                message_id,
                actor_profile_id,
                command_name,
                platform,
                target_platform_user_id,
                status,
                reason_code,
                redact_secrets(json.dumps(details or {}, ensure_ascii=False)),
                mysql_datetime(utc_now()),
            ),
        )

    async def _context_from_row(self, row: dict[str, Any]) -> V2RelationshipContext:
        profile = profile_from_row(row)
        account = account_from_row(row)
        social_labels = await self._list_social_labels(profile_id=profile.id)
        return build_relationship_context(
            profile=profile,
            platform_account=account,
            social_labels=social_labels,
        )

    async def _fetch_conversation_persona_row(
        self,
        *,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        return await self._fetchone(
            """
            SELECT
                p.id AS persona_id,
                p.code AS persona_code,
                p.display_name AS persona_display_name,
                p.description AS persona_description,
                p.status AS persona_status,
                p.default_for_admin,
                p.default_for_normal_friend,
                p.created_at AS persona_created_at,
                p.updated_at AS persona_updated_at,
                pv.id AS persona_version_id,
                pv.version_label,
                pv.prompt_template,
                pv.style_rules_json,
                pv.safety_rules_json,
                pv.memory_policy_json,
                pv.active AS version_active,
                pv.created_by_profile_id,
                pv.created_at AS version_created_at,
                cps.state_json
            FROM conversation_persona_state cps
            INNER JOIN personas p ON p.id = cps.persona_id
            LEFT JOIN persona_versions pv
                ON pv.id = cps.active_persona_version_id
                OR (cps.active_persona_version_id IS NULL AND pv.persona_id = p.id AND pv.active = TRUE)
            WHERE cps.conversation_id = %s
              AND p.status = 'active'
              AND p.code = 'hutao_v1'
            ORDER BY pv.active DESC, pv.created_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        )

    async def _fetch_bound_persona_row(
        self,
        *,
        relationship_context: V2RelationshipContext,
        platform_thread_id: str | None,
    ) -> dict[str, Any] | None:
        return await self._fetchone(
            """
            SELECT
                p.id AS persona_id,
                p.code AS persona_code,
                p.display_name AS persona_display_name,
                p.description AS persona_description,
                p.status AS persona_status,
                p.default_for_admin,
                p.default_for_normal_friend,
                p.created_at AS persona_created_at,
                p.updated_at AS persona_updated_at,
                pv.id AS persona_version_id,
                pv.version_label,
                pv.prompt_template,
                pv.style_rules_json,
                pv.safety_rules_json,
                pv.memory_policy_json,
                pv.active AS version_active,
                pv.created_by_profile_id,
                pv.created_at AS version_created_at,
                b.scope AS binding_scope,
                NULL AS state_json
            FROM persona_runtime_bindings b
            INNER JOIN personas p ON p.id = b.persona_id
            LEFT JOIN persona_versions pv ON pv.persona_id = p.id AND pv.active = TRUE
            WHERE b.enabled = TRUE
              AND p.status = 'active'
              AND p.code = 'hutao_v1'
              AND (
                  (b.scope = 'profile' AND b.profile_id = %s)
                  OR (b.scope = 'relationship_type' AND b.relationship_type = %s)
                  OR (
                      b.scope = 'platform'
                      AND b.platform = %s
                      AND (b.platform_thread_id IS NULL OR b.platform_thread_id = %s)
                  )
                  OR (
                      b.scope = 'conversation'
                      AND b.platform = %s
                      AND b.platform_thread_id = %s
                  )
                  OR b.scope = 'global'
              )
            ORDER BY
                CASE b.scope
                    WHEN 'conversation' THEN 1
                    WHEN 'profile' THEN 2
                    WHEN 'relationship_type' THEN 3
                    WHEN 'platform' THEN 4
                    WHEN 'global' THEN 5
                    ELSE 9
                END,
                b.priority ASC,
                pv.created_at DESC
            LIMIT 1
            """,
            (
                relationship_context.profile.id,
                relationship_context.effective_relationship_type,
                relationship_context.platform_account.platform,
                platform_thread_id or relationship_context.platform_account.platform_group_id,
                relationship_context.platform_account.platform,
                platform_thread_id or relationship_context.platform_account.platform_group_id,
            ),
        )

    async def _fetch_default_persona_row(
        self,
        *,
        relationship_type: RelationshipType,
    ) -> dict[str, Any] | None:
        return await self._fetchone(
            """
            SELECT
                p.id AS persona_id,
                p.code AS persona_code,
                p.display_name AS persona_display_name,
                p.description AS persona_description,
                p.status AS persona_status,
                p.default_for_admin,
                p.default_for_normal_friend,
                p.created_at AS persona_created_at,
                p.updated_at AS persona_updated_at,
                pv.id AS persona_version_id,
                pv.version_label,
                pv.prompt_template,
                pv.style_rules_json,
                pv.safety_rules_json,
                pv.memory_policy_json,
                pv.active AS version_active,
                pv.created_by_profile_id,
                pv.created_at AS version_created_at,
                NULL AS state_json
            FROM personas p
            LEFT JOIN persona_versions pv ON pv.persona_id = p.id AND pv.active = TRUE
            WHERE p.status = 'active'
              AND p.code = 'hutao_v1'
              AND (
                  (%s = 'admin_partner' AND p.default_for_admin = TRUE)
                  OR (%s <> 'admin_partner' AND p.default_for_normal_friend = TRUE)
              )
            ORDER BY p.updated_at DESC, pv.created_at DESC
            LIMIT 1
            """,
            (relationship_type, relationship_type),
        )
    async def _fetch_conversation(self, *, conversation_id: str) -> dict[str, Any] | None:
        return await self._fetchone(
            """
            SELECT id, platform, conversation_type, platform_thread_id,
                   owner_profile_id, title, created_at, updated_at
            FROM conversations
            WHERE id = %s
            LIMIT 1
            """,
            (conversation_id,),
        )

    async def _touch_conversation(self, *, conversation_id: str, timestamp: str) -> None:
        await self._execute(
            """
            UPDATE conversations
            SET updated_at = %s
            WHERE id = %s
            """,
            (mysql_datetime(timestamp), conversation_id),
        )

    async def _find_platform_account_id(
        self,
        *,
        profile_id: str | None,
        platform: str,
        user_id: str,
    ) -> str | None:
        if profile_id is None or platform not in {"qq", "wechat"}:
            return None
        chat_identity = infer_chat_identity(user_id=user_id, client_session_id="")
        row = await self._fetchone(
            """
            SELECT id
            FROM platform_accounts
            WHERE profile_id = %s
              AND platform = %s
              AND (%s = '' OR platform_user_id = %s)
            ORDER BY is_primary DESC, updated_at DESC
            LIMIT 1
            """,
            (
                profile_id,
                platform,
                str(chat_identity["platform_user_id"] or ""),
                str(chat_identity["platform_user_id"] or ""),
            ),
        )
        return str(row["id"]) if row is not None else None

    async def _profile_id_for_chat_user(
        self,
        *,
        user_id: str,
        session_id: str | None,
    ) -> str | None:
        if session_id:
            conversation = await self._fetch_conversation(conversation_id=session_id)
            if conversation and conversation.get("owner_profile_id") is not None:
                return str(conversation["owner_profile_id"])

        chat_identity = infer_chat_identity(user_id=user_id, client_session_id="")
        if chat_identity["platform"] == "core":
            return await self._active_core_profile_id(user_id=user_id)
        if chat_identity["platform"] not in {"qq", "wechat"} or not chat_identity["platform_user_id"]:
            return None
        row = await self._fetch_profile_account_row(
            platform=chat_identity["platform"],  # type: ignore[arg-type]
            platform_user_id=str(chat_identity["platform_user_id"]),
            platform_group_id="",
        )
        return str(row["profile_id"]) if row is not None else None

    async def _active_core_profile_id(self, *, user_id: str) -> str | None:
        row = await self._fetchone(
            """
            SELECT id
            FROM profiles
            WHERE id = %s
              AND status = 'active'
            LIMIT 1
            """,
            (user_id,),
        )
        return str(row["id"]) if row is not None else None

    async def _fetch_profile_account_row(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        platform_group_id: str,
    ) -> dict[str, Any] | None:
        return await self._fetchone(
            """
            SELECT
                p.id,
                p.display_name,
                p.relationship_type,
                p.verified,
                p.trust_level,
                p.affection_level,
                p.notes,
                p.status,
                p.merged_into_profile_id,
                p.created_at,
                p.updated_at,
                a.id AS account_id,
                a.profile_id,
                a.platform,
                a.platform_user_id,
                a.platform_group_id,
                a.display_name AS account_display_name,
                a.account_label,
                a.is_primary,
                a.status AS account_status,
                a.confidence,
                a.verified_by_profile_id,
                a.last_seen_at,
                a.created_at AS account_created_at,
                a.updated_at AS account_updated_at
            FROM platform_accounts a
            INNER JOIN profiles p ON p.id = a.profile_id
            WHERE a.platform = %s
              AND a.platform_user_id = %s
              AND a.platform_group_id = %s
              AND p.status <> 'deleted'
            LIMIT 1
            """,
            (platform, platform_user_id, platform_group_id),
        )

    async def _fetch_relationship_claim(
        self,
        *,
        claim_id: str,
    ) -> V2PendingRelationshipClaim | None:
        row = await self._fetchone(
            """
            SELECT
                id,
                platform,
                platform_user_id,
                claimed_name,
                claimed_relation_text,
                status,
                reviewed_by_profile_id,
                created_at,
                reviewed_at
            FROM relationship_pending_claims
            WHERE id = %s
            LIMIT 1
            """,
            (claim_id,),
        )
        return pending_claim_from_row(row) if row is not None else None

    async def _insert_platform_account(
        self,
        *,
        profile_id: str,
        platform: PlatformName,
        platform_user_id: str,
        platform_group_id: str,
        display_name: str,
        account_label: str,
        is_primary: bool,
        status: str,
        confidence: int,
        verified_by_profile_id: str | None,
        timestamp: str,
    ) -> str:
        account_id = new_uuid()
        await self._execute(
            """
            INSERT INTO platform_accounts (
                id, profile_id, platform, platform_user_id, platform_group_id,
                display_name, account_label, is_primary, status, confidence,
                verified_by_profile_id, last_seen_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                account_id,
                profile_id,
                platform,
                platform_user_id.strip(),
                normalize_platform_group_id(platform_group_id),
                display_name.strip() or platform_user_id.strip(),
                account_label,
                is_primary,
                status,
                confidence,
                verified_by_profile_id,
                mysql_datetime(timestamp),
                mysql_datetime(timestamp),
                mysql_datetime(timestamp),
            ),
        )
        return account_id

    async def _record_relationship_event(
        self,
        *,
        profile_id: str,
        event_type: str,
        platform: str | None = None,
        platform_user_id: str | None = None,
        old_value: dict[str, object] | None = None,
        new_value: dict[str, object] | None = None,
        changed_by_profile_id: str | None = None,
        reason: str = "",
        timestamp: str | None = None,
    ) -> None:
        created_at = timestamp or utc_now()
        await self._execute(
            """
            INSERT INTO relationship_events (
                id, profile_id, platform, platform_user_id, event_type,
                old_value, new_value, changed_by_profile_id, reason, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                new_uuid(),
                profile_id,
                platform,
                platform_user_id,
                event_type,
                json.dumps(old_value, ensure_ascii=False) if old_value is not None else None,
                json.dumps(new_value, ensure_ascii=False) if new_value is not None else None,
                changed_by_profile_id,
                redact_secrets(reason),
                mysql_datetime(created_at),
            ),
        )

    async def _list_social_labels(self, *, profile_id: str) -> tuple[str, ...]:
        rows = await self._fetchall(
            """
            SELECT label_type, label_text
            FROM profile_social_labels
            WHERE profile_id = %s
            ORDER BY created_at DESC
            LIMIT 8
            """,
            (profile_id,),
        )
        labels = []
        for row in rows:
            label_type = str(row["label_type"])
            label_text = str(row.get("label_text") or "")
            labels.append(label_type + (":" + label_text if label_text else ""))
        return tuple(labels)


def _is_hutao_persona_row(row: dict[str, Any] | None) -> bool:
    if row is None:
        return False
    return str(row.get("persona_code") or row.get("code") or "") == "hutao_v1"


def clean_ids(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def default_trust_level(relationship_type: RelationshipType) -> int:
    return {
        "admin_partner": 100,
        "normal_friend": 25,
        "blocked": 0,
    }[relationship_type]


def default_affection_level(relationship_type: RelationshipType) -> int:
    return {
        "admin_partner": 100,
        "normal_friend": 25,
        "blocked": 0,
    }[relationship_type]


def bounded_limit(value: int, *, default: int, maximum: int) -> int:
    if value <= 0:
        return default
    return min(value, maximum)


def infer_chat_identity(*, user_id: str, client_session_id: str) -> dict[str, object]:
    if user_id.startswith("qq-"):
        platform_user_id = user_id.removeprefix("qq-")
        platform_group_id = ""
        conversation_type = "private"
        if client_session_id.startswith("qq-group-") and "-user-" in client_session_id:
            conversation_type = "group"
            platform_group_id = client_session_id.removeprefix("qq-group-").split("-user-", 1)[0]
        return {
            "platform": "qq",
            "platform_user_id": platform_user_id,
            "platform_group_id": platform_group_id,
            "conversation_type": conversation_type,
        }
    if user_id.startswith("wechat-"):
        return {
            "platform": "wechat",
            "platform_user_id": user_id.removeprefix("wechat-"),
            "platform_group_id": "",
            "conversation_type": "private",
        }
    return {
        "platform": "core",
        "platform_user_id": "",
        "platform_group_id": "",
        "conversation_type": "private",
    }


def normalize_message_platform(value: str) -> str:
    return value if value in {"core", "qq", "wechat"} else "core"


def legacy_message_from_v2_row(row: dict[str, Any]) -> MessageRecord:
    role = str(row["role"])
    if role not in {"user", "assistant"}:
        role = "assistant"
    return MessageRecord(
        id=str(row["id"]),
        session_id=str(row["conversation_id"]),
        user_id=str(row.get("profile_id") or ""),
        role=role,  # type: ignore[arg-type]
        content=str(row.get("content") or ""),
        content_hash=str(row["content_hash"]),
        model_invocation_id=(
            str(row["model_invocation_id"]) if row.get("model_invocation_id") is not None else None
        ),
        created_at=str(row["created_at"]),
    )


def legacy_contact_from_v2_context(context: V2RelationshipContext) -> ContactRecord:
    relationship_role = {
        "admin_partner": "owner",
        "normal_friend": "friend",
        "blocked": "blocked",
    }[context.effective_relationship_type]
    return ContactRecord(
        id=context.profile.id,
        display_name=context.profile.display_name,
        relationship_role=relationship_role,  # type: ignore[arg-type]
        authority_level=100 if relationship_role == "owner" else 0 if relationship_role == "blocked" else 25,
        affection_level=context.profile.affection_level,
        trust_level=context.profile.trust_level,
        notes=context.profile.notes,
        created_at=context.profile.created_at,
        updated_at=context.profile.updated_at,
    )


def legacy_role_to_v2_relationship(value: str) -> RelationshipType:
    if value in {"owner", "admin_partner"}:
        return "admin_partner"
    if value == "blocked":
        return "blocked"
    return "normal_friend"
