from __future__ import annotations

import inspect
import json
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.database_control.errors import (
    ResourceConflictError,
    ResourceNotFoundError,
    translate_database_exception,
)
from app.database_control.persona_persistence import (
    PersonaBindingRow,
    PersonaDraftRow,
    PersonaReleaseRow,
    PersonaValidationRow,
    PersonaVersionRow,
    utc_now,
)
from app.storage.mysql_repository import MySQLChatRepository


class MySQLPersonaPersistenceStore(MySQLChatRepository):
    """Durable S5 store backed by the v2.003 persona-management schema."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    @property
    def backend_name(self) -> str:
        return "mysql-v2-persona-management"

    @property
    def durable(self) -> bool:
        return True

    async def create_draft(self, draft: PersonaDraftRow) -> PersonaDraftRow:
        try:
            await self._execute(
                """
                INSERT INTO persona_management_drafts (
                    draft_id, profile_id, definition_json, status,
                    created_by_profile_id, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    draft.draft_id,
                    draft.profile_id,
                    draft.definition_json,
                    draft.status,
                    draft.created_by_profile_id,
                    draft.created_at,
                    draft.created_at,
                ),
            )
        except Exception as exc:
            _raise_database_error(exc)
        return draft

    async def get_draft(self, draft_id: str) -> PersonaDraftRow | None:
        row = await self._fetchone(
            """
            SELECT draft_id, profile_id, definition_json, status,
                   created_by_profile_id, created_at
            FROM persona_management_drafts
            WHERE draft_id = %s
            LIMIT 1
            """,
            (draft_id,),
        )
        return _draft_row(row) if row else None

    async def list_drafts(self) -> tuple[PersonaDraftRow, ...]:
        rows = await self._fetchall(
            """
            SELECT draft_id, profile_id, definition_json, status,
                   created_by_profile_id, created_at
            FROM persona_management_drafts
            ORDER BY updated_at DESC, draft_id
            """,
            (),
        )
        return tuple(_draft_row(row) for row in rows)

    async def update_draft_status(self, draft_id: str, status: str) -> PersonaDraftRow:
        affected = await self._execute(
            """
            UPDATE persona_management_drafts
            SET status = %s, updated_at = CURRENT_TIMESTAMP(3)
            WHERE draft_id = %s
            """,
            (status, draft_id),
        )
        if not affected and await self.get_draft(draft_id) is None:
            raise ResourceNotFoundError("persona draft does not exist")
        row = await self.get_draft(draft_id)
        if row is None:
            raise ResourceNotFoundError("persona draft does not exist")
        return row

    async def save_validation(self, validation: PersonaValidationRow) -> None:
        try:
            await self._execute(
                """
                INSERT INTO persona_management_validations (
                    draft_id, stage, passed, errors_json, evaluated_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    passed = VALUES(passed),
                    errors_json = VALUES(errors_json),
                    evaluated_at = VALUES(evaluated_at)
                """,
                (
                    validation.draft_id,
                    validation.stage,
                    validation.passed,
                    json.dumps(validation.errors, ensure_ascii=False),
                    validation.evaluated_at,
                ),
            )
        except Exception as exc:
            _raise_database_error(exc)

    async def list_validations(self, draft_id: str) -> tuple[PersonaValidationRow, ...]:
        rows = await self._fetchall(
            """
            SELECT draft_id, stage, passed, errors_json, evaluated_at
            FROM persona_management_validations
            WHERE draft_id = %s
            ORDER BY evaluated_at, stage
            """,
            (draft_id,),
        )
        return tuple(_validation_row(row) for row in rows)

    async def create_version(
        self,
        *,
        draft_id: str,
        approved_by_profile_id: str,
    ) -> PersonaVersionRow:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(
                """
                SELECT draft_id, profile_id, definition_json, status,
                       created_by_profile_id, created_at
                FROM persona_management_drafts
                WHERE draft_id = %s
                FOR UPDATE
                """,
                (draft_id,),
            )
            draft = await cursor.fetchone()
            if draft is None:
                raise ResourceNotFoundError("persona draft does not exist")
            await cursor.execute(
                """
                SELECT version_id, profile_id, version_number, definition_json,
                       source_draft_id, approved_by_profile_id, created_at
                FROM persona_management_versions
                WHERE source_draft_id = %s
                LIMIT 1
                """,
                (draft_id,),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                await connection.commit()
                return _version_row(existing)
            await cursor.execute(
                """
                SELECT version_number
                FROM persona_management_versions
                WHERE profile_id = %s
                ORDER BY version_number DESC
                LIMIT 1
                FOR UPDATE
                """,
                (draft["profile_id"],),
            )
            maximum = await cursor.fetchone()
            version_number = (int(maximum["version_number"]) if maximum else 0) + 1
            version_id = f"{draft['profile_id']}@{version_number}"
            created_at = utc_now()
            await cursor.execute(
                """
                INSERT INTO persona_management_versions (
                    version_id, profile_id, version_number, definition_json,
                    source_draft_id, approved_by_profile_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    draft["profile_id"],
                    version_number,
                    draft["definition_json"],
                    draft_id,
                    approved_by_profile_id,
                    created_at,
                ),
            )
            await connection.commit()
            return PersonaVersionRow(
                version_id=version_id,
                profile_id=str(draft["profile_id"]),
                version=version_number,
                definition_json=_json_text(draft["definition_json"]),
                source_draft_id=draft_id,
                approved_by_profile_id=approved_by_profile_id,
                created_at=created_at,
            )
        except Exception as exc:
            await connection.rollback()
            _raise_database_error(exc)
        finally:
            await _close_cursor(cursor)
            connection.close()

    async def get_version(self, version_id: str) -> PersonaVersionRow | None:
        row = await self._fetchone(
            """
            SELECT version_id, profile_id, version_number, definition_json,
                   source_draft_id, approved_by_profile_id, created_at
            FROM persona_management_versions
            WHERE version_id = %s
            LIMIT 1
            """,
            (version_id,),
        )
        return _version_row(row) if row else None

    async def list_versions(self, profile_id: str) -> tuple[PersonaVersionRow, ...]:
        rows = await self._fetchall(
            """
            SELECT version_id, profile_id, version_number, definition_json,
                   source_draft_id, approved_by_profile_id, created_at
            FROM persona_management_versions
            WHERE profile_id = %s
            ORDER BY version_number
            """,
            (profile_id,),
        )
        return tuple(_version_row(row) for row in rows)

    async def list_all_versions(self) -> tuple[PersonaVersionRow, ...]:
        rows = await self._fetchall(
            """
            SELECT version_id, profile_id, version_number, definition_json,
                   source_draft_id, approved_by_profile_id, created_at
            FROM persona_management_versions
            ORDER BY profile_id, version_number
            """,
            (),
        )
        return tuple(_version_row(row) for row in rows)

    async def activate_version(
        self,
        *,
        profile_id: str,
        version_id: str,
        actor_profile_id: str,
        operation_id: str,
        rollback: bool = False,
    ) -> PersonaReleaseRow:
        connection = await self._connect()
        cursor = connection.cursor()
        operation_type = "rollback" if rollback else "publish"
        try:
            await cursor.execute(
                """
                SELECT operation_id, operation_type, profile_id, version_id, release_id
                FROM persona_management_operations
                WHERE operation_id = %s
                FOR UPDATE
                """,
                (operation_id,),
            )
            operation = await cursor.fetchone()
            if operation is not None:
                if (
                    str(operation["operation_type"]) != operation_type
                    or str(operation["profile_id"]) != profile_id
                    or str(operation["version_id"]) != version_id
                ):
                    raise ResourceConflictError(
                        "persona operation id was reused with another request"
                    )
                release = await _fetch_release(cursor, str(operation["release_id"]))
                await connection.commit()
                return release

            await cursor.execute(
                """
                SELECT version_id, profile_id
                FROM persona_management_versions
                WHERE version_id = %s
                FOR UPDATE
                """,
                (version_id,),
            )
            version = await cursor.fetchone()
            if version is None:
                raise ResourceNotFoundError("persona version does not exist")
            if str(version["profile_id"]) != profile_id:
                raise ResourceConflictError("persona version belongs to another profile")

            await cursor.execute(
                """
                SELECT release_id, profile_id, version_id, status, operation_id,
                       actor_profile_id, replaced_release_id, rollback_of_release_id,
                       created_at
                FROM persona_management_releases
                WHERE profile_id = %s AND status = 'active'
                LIMIT 1
                FOR UPDATE
                """,
                (profile_id,),
            )
            active_data = await cursor.fetchone()
            active = _release_row(active_data) if active_data else None
            if active is not None and active.version_id == version_id:
                await _insert_operation(
                    cursor,
                    operation_id=operation_id,
                    operation_type=operation_type,
                    profile_id=profile_id,
                    version_id=version_id,
                    release_id=active.release_id,
                    actor_profile_id=actor_profile_id,
                )
                await connection.commit()
                return active

            if active is not None:
                await cursor.execute(
                    """
                    UPDATE persona_management_releases
                    SET status = %s
                    WHERE release_id = %s AND status = 'active'
                    """,
                    ("rolled_back" if rollback else "superseded", active.release_id),
                )
            release = PersonaReleaseRow(
                release_id=uuid4().hex,
                profile_id=profile_id,
                version_id=version_id,
                status="active",
                operation_id=operation_id,
                actor_profile_id=actor_profile_id,
                replaced_release_id=active.release_id if active else None,
                rollback_of_release_id=active.release_id if rollback and active else None,
                created_at=utc_now(),
            )
            await cursor.execute(
                """
                INSERT INTO persona_management_releases (
                    release_id, profile_id, version_id, status, operation_id,
                    actor_profile_id, replaced_release_id, rollback_of_release_id,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    release.release_id,
                    release.profile_id,
                    release.version_id,
                    release.status,
                    release.operation_id,
                    release.actor_profile_id,
                    release.replaced_release_id,
                    release.rollback_of_release_id,
                    release.created_at,
                ),
            )
            await _insert_operation(
                cursor,
                operation_id=operation_id,
                operation_type=operation_type,
                profile_id=profile_id,
                version_id=version_id,
                release_id=release.release_id,
                actor_profile_id=actor_profile_id,
            )
            await connection.commit()
            return release
        except Exception as exc:
            await connection.rollback()
            _raise_database_error(exc)
        finally:
            await _close_cursor(cursor)
            connection.close()

    async def get_active_release(self, profile_id: str) -> PersonaReleaseRow | None:
        row = await self._fetchone(
            """
            SELECT release_id, profile_id, version_id, status, operation_id,
                   actor_profile_id, replaced_release_id, rollback_of_release_id,
                   created_at
            FROM persona_management_releases
            WHERE profile_id = %s AND status = 'active'
            LIMIT 1
            """,
            (profile_id,),
        )
        return _release_row(row) if row else None

    async def list_releases(self, profile_id: str) -> tuple[PersonaReleaseRow, ...]:
        rows = await self._fetchall(
            """
            SELECT release_id, profile_id, version_id, status, operation_id,
                   actor_profile_id, replaced_release_id, rollback_of_release_id,
                   created_at
            FROM persona_management_releases
            WHERE profile_id = %s
            ORDER BY created_at
            """,
            (profile_id,),
        )
        return tuple(_release_row(row) for row in rows)

    async def list_all_releases(self) -> tuple[PersonaReleaseRow, ...]:
        rows = await self._fetchall(
            """
            SELECT release_id, profile_id, version_id, status, operation_id,
                   actor_profile_id, replaced_release_id, rollback_of_release_id,
                   created_at
            FROM persona_management_releases
            ORDER BY created_at
            """,
            (),
        )
        return tuple(_release_row(row) for row in rows)

    async def save_binding(self, binding: PersonaBindingRow) -> PersonaBindingRow:
        connection = await self._connect()
        cursor = connection.cursor()
        try:
            await cursor.execute(
                """
                SELECT v.profile_id
                FROM persona_management_versions v
                JOIN persona_management_releases r
                  ON r.version_id = v.version_id AND r.status = 'active'
                WHERE v.version_id = %s
                LIMIT 1
                FOR UPDATE
                """,
                (binding.version_id,),
            )
            if await cursor.fetchone() is None:
                raise ResourceConflictError("persona binding version is not active")
            await cursor.execute(
                """
                SELECT binding_id
                FROM persona_management_bindings
                WHERE scope = %s AND scope_key = %s
                LIMIT 1
                FOR UPDATE
                """,
                (binding.scope, binding.scope_key),
            )
            scope_owner = await cursor.fetchone()
            if scope_owner is not None and str(scope_owner["binding_id"]) != binding.binding_id:
                raise ResourceConflictError("persona binding scope already exists")
            await cursor.execute(
                """
                INSERT INTO persona_management_bindings (
                    binding_id, scope, scope_key, version_id, surface_json,
                    enabled, updated_by_profile_id, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    scope = VALUES(scope),
                    scope_key = VALUES(scope_key),
                    version_id = VALUES(version_id),
                    surface_json = VALUES(surface_json),
                    enabled = VALUES(enabled),
                    updated_by_profile_id = VALUES(updated_by_profile_id),
                    updated_at = VALUES(updated_at)
                """,
                (
                    binding.binding_id,
                    binding.scope,
                    binding.scope_key,
                    binding.version_id,
                    binding.surface_json,
                    binding.enabled,
                    binding.updated_by_profile_id,
                    binding.updated_at,
                ),
            )
            await connection.commit()
            return binding
        except Exception as exc:
            await connection.rollback()
            _raise_database_error(exc)
        finally:
            await _close_cursor(cursor)
            connection.close()

    async def list_bindings(self) -> tuple[PersonaBindingRow, ...]:
        rows = await self._fetchall(
            """
            SELECT binding_id, scope, scope_key, version_id, surface_json,
                   enabled, updated_by_profile_id, updated_at
            FROM persona_management_bindings
            ORDER BY binding_id
            """,
            (),
        )
        return tuple(_binding_row(row) for row in rows)


async def _fetch_release(cursor: Any, release_id: str) -> PersonaReleaseRow:
    await cursor.execute(
        """
        SELECT release_id, profile_id, version_id, status, operation_id,
               actor_profile_id, replaced_release_id, rollback_of_release_id,
               created_at
        FROM persona_management_releases
        WHERE release_id = %s
        LIMIT 1
        """,
        (release_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise ResourceNotFoundError("persona release does not exist")
    return _release_row(row)


async def _insert_operation(
    cursor: Any,
    *,
    operation_id: str,
    operation_type: str,
    profile_id: str,
    version_id: str,
    release_id: str,
    actor_profile_id: str,
) -> None:
    await cursor.execute(
        """
        INSERT INTO persona_management_operations (
            operation_id, operation_type, profile_id, version_id,
            release_id, actor_profile_id, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP(3))
        """,
        (
            operation_id,
            operation_type,
            profile_id,
            version_id,
            release_id,
            actor_profile_id,
        ),
    )


async def _close_cursor(cursor: Any) -> None:
    result = cursor.close()
    if inspect.isawaitable(result):
        await result


def _draft_row(row: dict[str, Any]) -> PersonaDraftRow:
    return PersonaDraftRow(
        draft_id=str(row["draft_id"]),
        profile_id=str(row["profile_id"]),
        definition_json=_json_text(row["definition_json"]),
        status=str(row["status"]),
        created_by_profile_id=str(row["created_by_profile_id"]),
        created_at=row["created_at"],
    )


def _validation_row(row: dict[str, Any]) -> PersonaValidationRow:
    errors = json.loads(_json_text(row["errors_json"]))
    return PersonaValidationRow(
        draft_id=str(row["draft_id"]),
        stage=str(row["stage"]),
        passed=bool(row["passed"]),
        errors=tuple(str(error) for error in errors),
        evaluated_at=row["evaluated_at"],
    )


def _version_row(row: dict[str, Any]) -> PersonaVersionRow:
    return PersonaVersionRow(
        version_id=str(row["version_id"]),
        profile_id=str(row["profile_id"]),
        version=int(row["version_number"]),
        definition_json=_json_text(row["definition_json"]),
        source_draft_id=str(row["source_draft_id"]),
        approved_by_profile_id=str(row["approved_by_profile_id"]),
        created_at=row["created_at"],
    )


def _release_row(row: dict[str, Any]) -> PersonaReleaseRow:
    return PersonaReleaseRow(
        release_id=str(row["release_id"]),
        profile_id=str(row["profile_id"]),
        version_id=str(row["version_id"]),
        status=str(row["status"]),
        operation_id=str(row["operation_id"]),
        actor_profile_id=str(row["actor_profile_id"]),
        replaced_release_id=(
            str(row["replaced_release_id"]) if row.get("replaced_release_id") else None
        ),
        rollback_of_release_id=(
            str(row["rollback_of_release_id"])
            if row.get("rollback_of_release_id")
            else None
        ),
        created_at=row["created_at"],
    )


def _binding_row(row: dict[str, Any]) -> PersonaBindingRow:
    return PersonaBindingRow(
        binding_id=str(row["binding_id"]),
        scope=str(row["scope"]),
        scope_key=str(row["scope_key"]),
        version_id=str(row["version_id"]),
        surface_json=_json_text(row["surface_json"]),
        enabled=bool(row["enabled"]),
        updated_by_profile_id=str(row["updated_by_profile_id"]),
        updated_at=row["updated_at"],
    )


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _raise_database_error(exc: Exception) -> None:
    if isinstance(exc, (ResourceConflictError, ResourceNotFoundError)):
        raise exc
    translated = translate_database_exception(exc)
    if translated is not None:
        raise translated from exc
    raise exc
