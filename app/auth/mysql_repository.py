from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.auth.service import AccountProfile, StoredSession, WebUser
from app.auth.registration import PendingWebUser
from app.auth.rate_limit import RateLimitState
from app.auth.audit import AuthAuditEvent
from app.storage.chat_repository import new_uuid
from app.storage.mysql_repository import mysql_datetime
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository


class MySQLAuthRepository(MySQLDatabaseV2Repository):
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
            ON DUPLICATE KEY UPDATE
                blocked_until = CASE
                    WHEN blocked_until > VALUES(updated_at) THEN blocked_until
                    WHEN attempt_count + 1 > %s THEN VALUES(updated_at) + INTERVAL %s SECOND
                    ELSE NULL
                END,
                attempt_count = attempt_count + 1,
                updated_at = VALUES(updated_at)
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
            close_result = cursor.close()
            if hasattr(close_result, "__await__"):
                await close_result
            connection.close()
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
            close_result = cursor.close()
            if hasattr(close_result, "__await__"):
                await close_result
            connection.close()

    async def find_user_by_email(self, *, email_normalized: str) -> WebUser | None:
        row = await self._fetchone(
            """
            SELECT id, profile_id, email_normalized, password_hash, status
            FROM web_users
            WHERE email_normalized = %s
            LIMIT 1
            """,
            (email_normalized,),
        )
        return _web_user_from_row(row) if row is not None else None

    async def create_password_reset_token(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        timestamp = mysql_datetime(created_at.isoformat())
        await self._execute(
            """
            UPDATE password_reset_tokens
            SET used_at = %s
            WHERE user_id = %s AND used_at IS NULL
            """,
            (timestamp, user_id),
        )
        await self._execute(
            """
            INSERT INTO password_reset_tokens (
                id, user_id, token_hash, expires_at, used_at, created_at
            )
            VALUES (%s, %s, %s, %s, NULL, %s)
            """,
            (
                new_uuid(),
                user_id,
                token_hash,
                mysql_datetime(expires_at.isoformat()),
                timestamp,
            ),
        )

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
            close_result = cursor.close()
            if hasattr(close_result, "__await__"):
                await close_result
            connection.close()

    async def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        csrf_secret_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> StoredSession:
        session_id = new_uuid()
        timestamp = mysql_datetime(created_at.isoformat())
        await self._execute(
            """
            INSERT INTO web_sessions (
                id, user_id, token_hash, csrf_secret_hash,
                expires_at, revoked_at, last_seen_at, created_at
            )
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s)
            """,
            (
                session_id,
                user_id,
                token_hash,
                csrf_secret_hash,
                mysql_datetime(expires_at.isoformat()),
                timestamp,
                timestamp,
            ),
        )
        return StoredSession(
            id=session_id,
            user_id=user_id,
            profile_id="",
            token_hash=token_hash,
            csrf_secret_hash=csrf_secret_hash,
            expires_at=expires_at,
            revoked_at=None,
        )

    async def find_session_by_token_hash(self, *, token_hash: str) -> StoredSession | None:
        row = await self._fetchone(
            """
            SELECT ws.id, ws.user_id, wu.profile_id, ws.token_hash, ws.csrf_secret_hash,
                   ws.expires_at, ws.revoked_at
            FROM web_sessions ws
            INNER JOIN web_users wu ON wu.id = ws.user_id
            WHERE ws.token_hash = %s
              AND wu.status = 'active'
            LIMIT 1
            """,
            (token_hash,),
        )
        return _stored_session_from_row(row) if row is not None else None

    async def find_account_by_user_id(self, *, user_id: str) -> AccountProfile | None:
        row = await self._fetchone(
            """
            SELECT wu.id AS user_id, wu.profile_id, wu.email_normalized,
                   wu.email_verified_at, wu.created_at, p.display_name
            FROM web_users wu
            INNER JOIN profiles p ON p.id = wu.profile_id
            WHERE wu.id = %s
              AND wu.status = 'active'
              AND p.status = 'active'
            LIMIT 1
            """,
            (user_id,),
        )
        if row is None:
            return None
        return AccountProfile(
            user_id=str(row["user_id"]),
            profile_id=str(row["profile_id"]),
            display_name=str(row["display_name"]),
            email_normalized=str(row["email_normalized"]),
            email_verified=row.get("email_verified_at") is not None,
            created_at=_as_utc_datetime(row["created_at"]),
        )

    async def revoke_session(self, *, session_id: str, revoked_at: datetime) -> None:
        await self._execute(
            """
            UPDATE web_sessions
            SET revoked_at = %s
            WHERE id = %s AND revoked_at IS NULL
            """,
            (mysql_datetime(revoked_at.isoformat()), session_id),
        )


def _web_user_from_row(row: dict[str, Any]) -> WebUser:
    return WebUser(
        id=str(row["id"]),
        profile_id=str(row["profile_id"]),
        email_normalized=str(row["email_normalized"]),
        password_hash=str(row["password_hash"]),
        status=str(row["status"]),
    )


def _stored_session_from_row(row: dict[str, Any]) -> StoredSession:
    return StoredSession(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        profile_id=str(row["profile_id"]),
        token_hash=str(row["token_hash"]),
        csrf_secret_hash=str(row["csrf_secret_hash"]),
        expires_at=_as_utc_datetime(row["expires_at"]),
        revoked_at=_as_utc_datetime(row["revoked_at"]) if row.get("revoked_at") else None,
    )


def _as_utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
