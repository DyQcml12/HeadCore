from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from app.database_control.errors import ResourceConflictError, ResourceNotFoundError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PersonaDraftRow:
    draft_id: str
    profile_id: str
    definition_json: str
    status: str
    created_by_profile_id: str
    created_at: datetime


@dataclass(frozen=True)
class PersonaValidationRow:
    draft_id: str
    stage: str
    passed: bool
    errors: tuple[str, ...]
    evaluated_at: datetime


@dataclass(frozen=True)
class PersonaVersionRow:
    version_id: str
    profile_id: str
    version: int
    definition_json: str
    source_draft_id: str
    approved_by_profile_id: str
    created_at: datetime


@dataclass(frozen=True)
class PersonaReleaseRow:
    release_id: str
    profile_id: str
    version_id: str
    status: str
    operation_id: str
    actor_profile_id: str
    replaced_release_id: str | None
    rollback_of_release_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class PersonaBindingRow:
    binding_id: str
    scope: str
    scope_key: str
    version_id: str
    surface_json: str
    enabled: bool
    updated_by_profile_id: str
    updated_at: datetime


class PersonaPersistenceStore(Protocol):
    @property
    def backend_name(self) -> str: ...

    @property
    def durable(self) -> bool: ...

    async def create_draft(self, draft: PersonaDraftRow) -> PersonaDraftRow: ...

    async def get_draft(self, draft_id: str) -> PersonaDraftRow | None: ...

    async def list_drafts(self) -> tuple[PersonaDraftRow, ...]: ...

    async def update_draft_status(self, draft_id: str, status: str) -> PersonaDraftRow: ...

    async def save_validation(self, validation: PersonaValidationRow) -> None: ...

    async def list_validations(self, draft_id: str) -> tuple[PersonaValidationRow, ...]: ...

    async def create_version(
        self,
        *,
        draft_id: str,
        approved_by_profile_id: str,
    ) -> PersonaVersionRow: ...

    async def get_version(self, version_id: str) -> PersonaVersionRow | None: ...

    async def list_versions(self, profile_id: str) -> tuple[PersonaVersionRow, ...]: ...

    async def list_all_versions(self) -> tuple[PersonaVersionRow, ...]: ...

    async def activate_version(
        self,
        *,
        profile_id: str,
        version_id: str,
        actor_profile_id: str,
        operation_id: str,
        rollback: bool = False,
    ) -> PersonaReleaseRow: ...

    async def get_active_release(self, profile_id: str) -> PersonaReleaseRow | None: ...

    async def list_releases(self, profile_id: str) -> tuple[PersonaReleaseRow, ...]: ...

    async def list_all_releases(self) -> tuple[PersonaReleaseRow, ...]: ...

    async def save_binding(self, binding: PersonaBindingRow) -> PersonaBindingRow: ...

    async def list_bindings(self) -> tuple[PersonaBindingRow, ...]: ...


class InMemoryPersonaPersistenceStore:
    """Transaction-semantic fake for future Database V2 implementations."""

    def __init__(self) -> None:
        self._drafts: dict[str, PersonaDraftRow] = {}
        self._validations: dict[str, dict[str, PersonaValidationRow]] = {}
        self._versions: dict[str, PersonaVersionRow] = {}
        self._releases: dict[str, PersonaReleaseRow] = {}
        self._active_release_ids: dict[str, str] = {}
        self._operation_releases: dict[str, tuple[str, str, str, bool]] = {}
        self._bindings: dict[str, PersonaBindingRow] = {}
        self._lock = asyncio.Lock()

    @property
    def backend_name(self) -> str:
        return "memory-transaction-fake"

    @property
    def durable(self) -> bool:
        return False

    async def create_draft(self, draft: PersonaDraftRow) -> PersonaDraftRow:
        async with self._lock:
            if draft.draft_id in self._drafts:
                raise ResourceConflictError("persona draft already exists")
            self._drafts[draft.draft_id] = draft
            self._validations[draft.draft_id] = {}
            return draft

    async def get_draft(self, draft_id: str) -> PersonaDraftRow | None:
        return self._drafts.get(draft_id)

    async def list_drafts(self) -> tuple[PersonaDraftRow, ...]:
        return tuple(self._drafts.values())

    async def update_draft_status(self, draft_id: str, status: str) -> PersonaDraftRow:
        async with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise ResourceNotFoundError("persona draft does not exist")
            updated = replace(draft, status=status)
            self._drafts[draft_id] = updated
            return updated

    async def save_validation(self, validation: PersonaValidationRow) -> None:
        async with self._lock:
            if validation.draft_id not in self._drafts:
                raise ResourceNotFoundError("persona draft does not exist")
            self._validations[validation.draft_id][validation.stage] = validation

    async def list_validations(self, draft_id: str) -> tuple[PersonaValidationRow, ...]:
        return tuple(self._validations.get(draft_id, {}).values())

    async def create_version(
        self,
        *,
        draft_id: str,
        approved_by_profile_id: str,
    ) -> PersonaVersionRow:
        async with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise ResourceNotFoundError("persona draft does not exist")
            existing = next(
                (version for version in self._versions.values() if version.source_draft_id == draft_id),
                None,
            )
            if existing is not None:
                return existing
            next_version = 1 + max(
                (
                    version.version
                    for version in self._versions.values()
                    if version.profile_id == draft.profile_id
                ),
                default=0,
            )
            version = PersonaVersionRow(
                version_id=f"{draft.profile_id}@{next_version}",
                profile_id=draft.profile_id,
                version=next_version,
                definition_json=draft.definition_json,
                source_draft_id=draft_id,
                approved_by_profile_id=approved_by_profile_id,
                created_at=utc_now(),
            )
            self._versions[version.version_id] = version
            return version

    async def get_version(self, version_id: str) -> PersonaVersionRow | None:
        return self._versions.get(version_id)

    async def list_versions(self, profile_id: str) -> tuple[PersonaVersionRow, ...]:
        return tuple(
            sorted(
                (version for version in self._versions.values() if version.profile_id == profile_id),
                key=lambda version: version.version,
            )
        )

    async def list_all_versions(self) -> tuple[PersonaVersionRow, ...]:
        return tuple(sorted(self._versions.values(), key=lambda version: version.version_id))

    async def activate_version(
        self,
        *,
        profile_id: str,
        version_id: str,
        actor_profile_id: str,
        operation_id: str,
        rollback: bool = False,
    ) -> PersonaReleaseRow:
        async with self._lock:
            previous_operation = self._operation_releases.get(operation_id)
            if previous_operation is not None:
                release_id, previous_profile, previous_version, previous_rollback = previous_operation
                if (previous_profile, previous_version, previous_rollback) != (
                    profile_id,
                    version_id,
                    rollback,
                ):
                    raise ResourceConflictError("persona operation id was reused with another request")
                return self._releases[release_id]
            version = self._versions.get(version_id)
            if version is None:
                raise ResourceNotFoundError("persona version does not exist")
            if version.profile_id != profile_id:
                raise ResourceConflictError("persona version belongs to another profile")
            active_id = self._active_release_ids.get(profile_id)
            active = self._releases.get(active_id) if active_id else None
            if active is not None and active.version_id == version_id:
                self._operation_releases[operation_id] = (
                    active.release_id,
                    profile_id,
                    version_id,
                    rollback,
                )
                return active
            if active is not None:
                previous_status = "rolled_back" if rollback else "superseded"
                self._releases[active.release_id] = replace(active, status=previous_status)
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
            self._releases[release.release_id] = release
            self._active_release_ids[profile_id] = release.release_id
            self._operation_releases[operation_id] = (
                release.release_id,
                profile_id,
                version_id,
                rollback,
            )
            return release

    async def get_active_release(self, profile_id: str) -> PersonaReleaseRow | None:
        release_id = self._active_release_ids.get(profile_id)
        return self._releases.get(release_id) if release_id else None

    async def list_releases(self, profile_id: str) -> tuple[PersonaReleaseRow, ...]:
        return tuple(release for release in self._releases.values() if release.profile_id == profile_id)

    async def list_all_releases(self) -> tuple[PersonaReleaseRow, ...]:
        return tuple(self._releases.values())

    async def save_binding(self, binding: PersonaBindingRow) -> PersonaBindingRow:
        async with self._lock:
            version = self._versions.get(binding.version_id)
            if version is None:
                raise ResourceNotFoundError("persona binding version does not exist")
            active = await self.get_active_release(version.profile_id)
            if active is None or active.version_id != binding.version_id:
                raise ResourceConflictError("persona binding version is not active")
            self._bindings[binding.binding_id] = binding
            return binding

    async def list_bindings(self) -> tuple[PersonaBindingRow, ...]:
        return tuple(self._bindings.values())
