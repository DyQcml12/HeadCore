from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.auth.audit import AuthAuditEvent
from app.auth.mysql_repository import MySQLAuthRepository, _as_utc_datetime
from app.auth.rate_limit import RateLimitState
from app.auth.registration import PendingWebUser
from app.auth.service import WebUser
from app.storage.chat_repository import new_uuid
from app.storage.mysql_repository import mysql_datetime
from app.storage.postgres_repository import PostgreSQLChatRepository


class PostgreSQLAuthRepository(MySQLAuthRepository):
    """PostgreSQL implementation of the existing public-web auth contracts."""

    def __init__(self, settings) -> None:  # type: ignore[no-untyped-def]
        self.settings = settings
        self._validate_settings()

    _validate_settings = PostgreSQLChatRepository._validate_settings
    _connect = PostgreSQLChatRepository._connect
    _execute = PostgreSQLChatRepository._execute
    _fetchone = PostgreSQLChatRepository._fetchone
    _fetchall = PostgreSQLChatRepository._fetchall

    async def record(self, event: AuthAuditEvent) -> None:
        timestamp = mysql_datetime(datetime.now(timezone.utc).isoformat())
        await self._execute(
            """
            INSERT INTO auth_audit_events (
                id, user_id, event_type, outcome, reason_code, metadata, created_at
            )
            VALUES (%s, %s, %s, %s, %s, NULL, %s)
            """,
            (
                new_uuid(),
                event.user_id,
                event.event_type,
                event.outcome,
                event.reason_code,
                timestamp,
            ),
        )

    async def record_attempt(
        self,
        *,
        subject_kind: str,
        subject_hash: str,
        window_started_at: datetime,
        now: datetime,
        limit: int,
        blocked_until: datetime,
    ) -> RateLimitState:
        timestamp = mysql_datetime(now.isoformat())
        await self._execute(
            """
            INSERT INTO registration_attempts (
                id, subject_kind, subject_hash, window_started_at,
                attempt_count, blocked_until, updated_at
            )
            VALUES (%s, %s, %s, %s, 1, NULL, %s)
            ON CONFLICT (subject_kind, subject_hash, window_started_at) DO UPDATE
            SET blocked_until = CASE
                    WHEN registration_attempts.blocked_until > EXCLUDED.updated_at
                        THEN registration_attempts.blocked_until
                    WHEN registration_attempts.attempt_count + 1 > %s
                        THEN EXCLUDED.updated_at + (%s * INTERVAL '1 second')
                    ELSE NULL
                END,
                attempt_count = registration_attempts.attempt_count + 1,
                updated_at = EXCLUDED.updated_at
            """,
            (
                new_uuid(),
                subject_kind,
                subject_hash,
                mysql_datetime(window_started_at.isoformat()),
                timestamp,
                limit,
                int((blocked_until - now).total_seconds()),
            ),
        )
        row = await self._fetchone(
            """
            SELECT attempt_count, blocked_until
            FROM registration_attempts
            WHERE subject_kind = %s AND subject_hash = %s AND window_started_at = %s
            LIMIT 1
            """,
            (subject_kind, subject_hash, mysql_datetime(window_started_at.isoformat())),
        )
        if row is None:
            raise RuntimeError("rate limit state was not persisted")
        return RateLimitState(
            attempt_count=int(row["attempt_count"]),
            blocked_until=_as_utc_datetime(row["blocked_until"])
            if row.get("blocked_until") is not None
            else None,
        )

    async def create_pending_user(
        self,
        *,
        email_normalized: str,
        display_name: str,
        password_hash: str,
        verification_token_hash: str,
        verification_expires_at: datetime,
        created_at: datetime,
    ) -> PendingWebUser:
        profile_id = new_uuid()
        user_id = new_uuid()
        verification_id = new_uuid()
        created = mysql_datetime(created_at.isoformat())
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(
                """
                INSERT INTO profiles (
                    id, display_name, relationship_type, verified, created_at, updated_at
                )
                VALUES (%s, %s, 'normal_friend', FALSE, %s, %s)
                """,
                (profile_id, display_name, created, created),
            )
            await cursor.execute(
                """
                INSERT INTO web_users (
                    id, profile_id, email_normalized, password_hash, status,
                    email_verified_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, 'pending_email_verification', NULL, %s, %s)
                """,
                (user_id, profile_id, email_normalized, password_hash, created, created),
            )
            await cursor.execute(
                """
                INSERT INTO email_verification_tokens (
                    id, user_id, token_hash, expires_at, used_at, created_at
                )
                VALUES (%s, %s, %s, %s, NULL, %s)
                """,
                (
                    verification_id,
                    user_id,
                    verification_token_hash,
                    mysql_datetime(verification_expires_at.isoformat()),
                    created,
                ),
            )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise
        finally:
            await cursor.close()
            await connection.close()
        return PendingWebUser(id=user_id, profile_id=profile_id, email_normalized=email_normalized)

    async def consume_email_verification_token(
        self, *, token_hash: str, now: datetime
    ) -> PendingWebUser | None:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(
                """
                SELECT evt.id, evt.user_id, evt.expires_at, evt.used_at,
                       wu.profile_id, wu.email_normalized, wu.status
                FROM email_verification_tokens evt
                INNER JOIN web_users wu ON wu.id = evt.user_id
                WHERE evt.token_hash = %s
                LIMIT 1 FOR UPDATE
                """,
                (token_hash,),
            )
            row = await cursor.fetchone()
            if row is None or row.get("used_at") is not None or _as_utc_datetime(row["expires_at"]) <= now:
                await connection.rollback()
                return None
            timestamp = mysql_datetime(now.isoformat())
            await cursor.execute(
                "UPDATE email_verification_tokens SET used_at = %s WHERE id = %s AND used_at IS NULL",
                (timestamp, row["id"]),
            )
            await cursor.execute(
                """
                UPDATE web_users
                SET status = 'active', email_verified_at = %s, updated_at = %s
                WHERE id = %s AND status = 'pending_email_verification'
                """,
                (timestamp, timestamp, row["user_id"]),
            )
            await connection.commit()
            return PendingWebUser(
                id=str(row["user_id"]),
                profile_id=str(row["profile_id"]),
                email_normalized=str(row["email_normalized"]),
            )
        except Exception:
            await connection.rollback()
            raise
        finally:
            await cursor.close()
            await connection.close()

    async def consume_password_reset_token(
        self,
        *,
        token_hash: str,
        password_hash: str,
        now: datetime,
    ) -> WebUser | None:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(
                """
                SELECT prt.id, prt.user_id, prt.expires_at, prt.used_at,
                       wu.profile_id, wu.email_normalized, wu.password_hash, wu.status
                FROM password_reset_tokens prt
                INNER JOIN web_users wu ON wu.id = prt.user_id
                WHERE prt.token_hash = %s
                LIMIT 1 FOR UPDATE
                """,
                (token_hash,),
            )
            row = await cursor.fetchone()
            if (
                row is None
                or row.get("used_at") is not None
                or str(row.get("status")) != "active"
                or _as_utc_datetime(row["expires_at"]) <= now
            ):
                await connection.rollback()
                return None
            timestamp = mysql_datetime(now.isoformat())
            await cursor.execute(
                """
                UPDATE password_reset_tokens
                SET used_at = %s
                WHERE id = %s AND used_at IS NULL
                """,
                (timestamp, row["id"]),
            )
            await cursor.execute(
                """
                UPDATE web_users
                SET password_hash = %s, updated_at = %s
                WHERE id = %s AND status = 'active'
                """,
                (password_hash, timestamp, row["user_id"]),
            )
            await cursor.execute(
                """
                UPDATE web_sessions
                SET revoked_at = %s
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (timestamp, row["user_id"]),
            )
            await connection.commit()
            return WebUser(
                id=str(row["user_id"]),
                profile_id=str(row["profile_id"]),
                email_normalized=str(row["email_normalized"]),
                password_hash=password_hash,
                status="active",
            )
        except Exception:
            await connection.rollback()
            raise
        finally:
            await cursor.close()
            await connection.close()
