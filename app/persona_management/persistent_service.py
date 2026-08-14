from __future__ import annotations

from uuid import uuid4

from app.database_control.persona_persistence import (
    PersonaBindingRow,
    PersonaDraftRow,
    PersonaPersistenceStore,
    PersonaReleaseRow,
    PersonaValidationRow,
    PersonaVersionRow,
    utc_now,
)
from app.persona_management.bindings import resolve_binding
from app.persona_management.codec import (
    decode_definition,
    decode_surface,
    encode_definition,
    encode_surface,
)
from app.persona_management.contracts import (
    BindingContext,
    BindingScope,
    DraftStatus,
    PersonaBinding,
    PersonaDefinition,
    PersonaDraft,
    PersonaManagementStatus,
    PersonaRelease,
    PersonaRuntimeProjection,
    PersonaValidationResult,
    PersonaVersion,
    ReleaseStatus,
    ValidationStage,
)
from app.persona_management.projection import build_runtime_projection
from app.persona_management.service import PersonaManagementError
from app.persona_management.validation import validate_gates, validate_schema


class PersistentPersonaManagementService:
    def __init__(self, store: PersonaPersistenceStore) -> None:
        self._store = store

    async def create_draft(
        self,
        definition: PersonaDefinition,
        *,
        actor_id: str,
        draft_id: str | None = None,
    ) -> PersonaDraft:
        row = PersonaDraftRow(
            draft_id=draft_id or uuid4().hex,
            profile_id=definition.profile_id,
            definition_json=encode_definition(definition),
            status=DraftStatus.DRAFT,
            created_by_profile_id=actor_id,
            created_at=utc_now(),
        )
        return _draft_from_row(await self._store.create_draft(row))

    async def validate_draft(self, draft_id: str) -> tuple[PersonaValidationResult, ...]:
        draft = await self._require_draft(draft_id)
        results = (validate_schema(draft.definition), validate_gates(draft.definition))
        for result in results:
            await self._store.save_validation(_validation_to_row(draft_id, result))
        if all(result.passed for result in results):
            await self._store.update_draft_status(draft_id, DraftStatus.SCHEMA_VALIDATED)
        return results

    async def record_evaluation(
        self,
        draft_id: str,
        result: PersonaValidationResult,
    ) -> PersonaDraft:
        draft = await self._require_draft(draft_id)
        if result.stage not in {ValidationStage.REGRESSION, ValidationStage.LIVE_ACCEPTANCE}:
            raise PersonaManagementError("unsupported_evaluation_stage")
        if draft.status not in {DraftStatus.SCHEMA_VALIDATED, DraftStatus.OFFLINE_EVALUATED}:
            raise PersonaManagementError("schema_validation_required")
        await self._store.save_validation(_validation_to_row(draft_id, result))
        if result.stage == ValidationStage.REGRESSION and result.passed:
            row = await self._store.update_draft_status(draft_id, DraftStatus.OFFLINE_EVALUATED)
            return _draft_from_row(row)
        return await self._require_draft(draft_id)

    async def approve(self, draft_id: str, *, actor_id: str) -> PersonaVersion:
        draft = await self._require_draft(draft_id)
        if draft.status in {DraftStatus.APPROVED, DraftStatus.PUBLISHED}:
            versions = await self._store.list_versions(draft.definition.profile_id)
            existing = next(
                (version for version in versions if version.source_draft_id == draft_id),
                None,
            )
            if existing is None:
                raise PersonaManagementError("version_not_found")
            return _version_from_row(existing)
        validations = {row.stage: row for row in await self._store.list_validations(draft_id)}
        required = {ValidationStage.SCHEMA, ValidationStage.GATE, ValidationStage.REGRESSION}
        if not all(stage in validations and validations[stage].passed for stage in required):
            raise PersonaManagementError("offline_validation_required")
        row = await self._store.create_version(
            draft_id=draft_id,
            approved_by_profile_id=actor_id,
        )
        await self._store.update_draft_status(draft_id, DraftStatus.APPROVED)
        return _version_from_row(row)

    async def publish(
        self,
        version_id: str,
        *,
        actor_id: str,
        operation_id: str,
    ) -> PersonaRelease:
        version = await self._require_version(version_id)
        row = await self._store.activate_version(
            profile_id=version.profile_id,
            version_id=version_id,
            actor_profile_id=actor_id,
            operation_id=operation_id,
        )
        await self._store.update_draft_status(version.source_draft_id, DraftStatus.PUBLISHED)
        return _release_from_row(row)

    async def rollback(
        self,
        profile_id: str,
        target_version_id: str,
        *,
        actor_id: str,
        operation_id: str,
    ) -> PersonaRelease:
        target = await self._require_version(target_version_id)
        if target.profile_id != profile_id:
            raise PersonaManagementError("rollback_profile_mismatch")
        releases = await self._store.list_releases(profile_id)
        if not any(release.version_id == target_version_id for release in releases):
            raise PersonaManagementError("rollback_target_not_released")
        return _release_from_row(
            await self._store.activate_version(
                profile_id=profile_id,
                version_id=target_version_id,
                actor_profile_id=actor_id,
                operation_id=operation_id,
                rollback=True,
            )
        )

    async def save_binding(self, binding: PersonaBinding, *, actor_id: str) -> PersonaBinding:
        _validate_binding(binding)
        row = PersonaBindingRow(
            binding_id=binding.binding_id,
            scope=binding.scope,
            scope_key=binding.scope_key,
            version_id=binding.version_id,
            surface_json=encode_surface(binding.surface),
            enabled=binding.active,
            updated_by_profile_id=actor_id,
            updated_at=utc_now(),
        )
        return _binding_from_row(await self._store.save_binding(row))

    async def get_runtime_projection(
        self,
        profile_id: str,
        context: BindingContext,
    ) -> PersonaRuntimeProjection:
        active = await self._store.get_active_release(profile_id)
        if active is None:
            raise PersonaManagementError("active_version_not_found")
        version = await self._require_version(active.version_id)
        bindings = tuple(_binding_from_row(row) for row in await self._store.list_bindings())
        binding = resolve_binding(bindings, context)
        if binding is not None and binding.version_id != version.version_id:
            binding = None
        return build_runtime_projection(version, binding)

    async def get_status(self) -> PersonaManagementStatus:
        drafts = await self._store.list_drafts()
        versions = await self._store.list_all_versions()
        releases = await self._store.list_all_releases()
        bindings = await self._store.list_bindings()
        active_profiles = tuple(
            sorted(
                {
                    version.profile_id
                    for version in versions
                    if (active := await self._store.get_active_release(version.profile_id))
                    and active.version_id == version.version_id
                }
            )
        )
        return PersonaManagementStatus(
            storage_backend=self._store.backend_name,
            durable=self._store.durable,
            write_ready=self._store.durable,
            draft_count=len(drafts),
            version_count=len(versions),
            release_count=len(releases),
            binding_count=len(bindings),
            active_profiles=active_profiles,
        )

    async def get_draft(self, draft_id: str) -> PersonaDraft:
        return await self._require_draft(draft_id)

    async def list_validations(
        self, draft_id: str
    ) -> tuple[PersonaValidationResult, ...]:
        await self._require_draft(draft_id)
        return tuple(
            PersonaValidationResult(
                stage=ValidationStage(row.stage), passed=row.passed, errors=row.errors
            )
            for row in await self._store.list_validations(draft_id)
        )

    async def list_versions(self, profile_id: str) -> tuple[PersonaVersion, ...]:
        return tuple(_version_from_row(row) for row in await self._store.list_versions(profile_id))

    async def list_releases(self, profile_id: str) -> tuple[PersonaRelease, ...]:
        return tuple(_release_from_row(row) for row in await self._store.list_releases(profile_id))

    async def get_version(self, version_id: str) -> PersonaVersion:
        return await self._require_version(version_id)

    async def list_bindings(self) -> tuple[PersonaBinding, ...]:
        return tuple(_binding_from_row(row) for row in await self._store.list_bindings())

    async def _require_draft(self, draft_id: str) -> PersonaDraft:
        row = await self._store.get_draft(draft_id)
        if row is None:
            raise PersonaManagementError("draft_not_found")
        return _draft_from_row(row)

    async def _require_version(self, version_id: str) -> PersonaVersion:
        row = await self._store.get_version(version_id)
        if row is None:
            raise PersonaManagementError("version_not_found")
        return _version_from_row(row)


def _draft_from_row(row: PersonaDraftRow) -> PersonaDraft:
    return PersonaDraft(
        draft_id=row.draft_id,
        definition=decode_definition(row.definition_json),
        status=DraftStatus(row.status),
        created_by=row.created_by_profile_id,
        created_at=row.created_at,
    )


def _version_from_row(row: PersonaVersionRow) -> PersonaVersion:
    return PersonaVersion(
        profile_id=row.profile_id,
        version=row.version,
        definition=decode_definition(row.definition_json),
        source_draft_id=row.source_draft_id,
        approved_by=row.approved_by_profile_id,
        created_at=row.created_at,
    )


def _release_from_row(row: PersonaReleaseRow) -> PersonaRelease:
    return PersonaRelease(
        release_id=row.release_id,
        version_id=row.version_id,
        status=ReleaseStatus(row.status),
        actor_id=row.actor_profile_id,
        created_at=row.created_at,
        replaced_release_id=row.replaced_release_id,
        rollback_of_release_id=row.rollback_of_release_id,
    )


def _validation_to_row(
    draft_id: str,
    result: PersonaValidationResult,
) -> PersonaValidationRow:
    return PersonaValidationRow(
        draft_id=draft_id,
        stage=result.stage,
        passed=result.passed,
        errors=result.errors,
        evaluated_at=utc_now(),
    )


def _binding_from_row(row: PersonaBindingRow) -> PersonaBinding:
    return PersonaBinding(
        binding_id=row.binding_id,
        scope=BindingScope(row.scope),
        scope_key=row.scope_key,
        version_id=row.version_id,
        surface=decode_surface(row.surface_json),
        active=row.enabled,
    )


def _validate_binding(binding: PersonaBinding) -> None:
    scope_key = binding.scope_key.strip()
    if binding.scope == BindingScope.GLOBAL and scope_key != "*":
        raise PersonaManagementError("global_binding_key_must_be_wildcard")
    if binding.scope != BindingScope.GLOBAL and not scope_key:
        raise PersonaManagementError("binding_scope_key_required")
    if any(key.strip().lower() == "profile_id" for key, _ in binding.surface):
        raise PersonaManagementError("surface_cannot_override_profile_id")
