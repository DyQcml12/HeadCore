from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from app.persona_management.contracts import (
    BindingContext,
    BindingScope,
    DraftStatus,
    PersonaBinding,
    PersonaManagementStatus,
    PersonaDefinition,
    PersonaDraft,
    PersonaRelease,
    PersonaRuntimeProjection,
    PersonaValidationResult,
    PersonaVersion,
    ReleaseStatus,
    ValidationStage,
)
from app.persona_management.bindings import resolve_binding
from app.persona_management.projection import build_runtime_projection
from app.persona_management.validation import validate_gates, validate_schema
from app.persona_management.repository import (
    InMemoryPersonaManagementRepository,
    PersonaManagementRepository,
)


class PersonaManagementError(ValueError):
    pass


class InMemoryPersonaManagementService:
    def __init__(self, repository: PersonaManagementRepository | None = None) -> None:
        self._repository = repository or InMemoryPersonaManagementRepository()

    def create_draft(
        self,
        definition: PersonaDefinition,
        *,
        actor_id: str,
        draft_id: str | None = None,
    ) -> PersonaDraft:
        draft = PersonaDraft(
            draft_id=draft_id or uuid4().hex,
            definition=definition,
            created_by=actor_id,
        )
        if self._repository.get_draft(draft.draft_id) is not None:
            raise PersonaManagementError("draft_already_exists")
        self._repository.save_draft(draft)
        return draft

    def validate_draft(self, draft_id: str) -> tuple[PersonaValidationResult, ...]:
        draft = self._get_draft(draft_id)
        results = (validate_schema(draft.definition), validate_gates(draft.definition))
        for result in results:
            self._repository.save_validation(draft_id, result)
        if all(result.passed for result in results):
            self._set_draft_status(draft_id, DraftStatus.SCHEMA_VALIDATED)
        return results

    def record_evaluation(
        self,
        draft_id: str,
        result: PersonaValidationResult,
    ) -> PersonaDraft:
        draft = self._get_draft(draft_id)
        if result.stage not in {ValidationStage.REGRESSION, ValidationStage.LIVE_ACCEPTANCE}:
            raise PersonaManagementError("unsupported_evaluation_stage")
        if draft.status not in {
            DraftStatus.SCHEMA_VALIDATED,
            DraftStatus.OFFLINE_EVALUATED,
        }:
            raise PersonaManagementError("schema_validation_required")
        self._repository.save_validation(draft_id, result)
        if result.stage == ValidationStage.REGRESSION and result.passed:
            return self._set_draft_status(draft_id, DraftStatus.OFFLINE_EVALUATED)
        return self._get_draft(draft_id)

    def approve(self, draft_id: str, *, actor_id: str) -> PersonaVersion:
        draft = self._get_draft(draft_id)
        if draft.status == DraftStatus.PUBLISHED:
            return self._version_for_draft(draft_id)
        if draft.status == DraftStatus.APPROVED:
            return self._version_for_draft(draft_id)
        validations = self._repository.get_validations(draft_id)
        required = {ValidationStage.SCHEMA, ValidationStage.GATE, ValidationStage.REGRESSION}
        if not required.issubset(validations) or not all(validations[stage].passed for stage in required):
            raise PersonaManagementError("offline_validation_required")
        version_number = 1 + max(
            (version.version for version in self._repository.list_versions(draft.definition.profile_id)),
            default=0,
        )
        version = PersonaVersion(
            profile_id=draft.definition.profile_id,
            version=version_number,
            definition=draft.definition,
            source_draft_id=draft_id,
            approved_by=actor_id,
        )
        self._repository.save_version(version)
        self._set_draft_status(draft_id, DraftStatus.APPROVED)
        return version

    def publish(self, version_id: str, *, actor_id: str) -> PersonaRelease:
        version = self._get_version(version_id)
        existing = self._active_release(version.profile_id)
        if existing and existing.version_id == version_id:
            return existing
        if existing:
            self._repository.save_release(replace(existing, status=ReleaseStatus.SUPERSEDED))
        release = PersonaRelease(
            release_id=uuid4().hex,
            version_id=version_id,
            status=ReleaseStatus.ACTIVE,
            actor_id=actor_id,
            replaced_release_id=existing.release_id if existing else None,
        )
        self._repository.save_release(release)
        self._repository.set_active_release(version.profile_id, release.release_id)
        self._set_draft_status(version.source_draft_id, DraftStatus.PUBLISHED)
        return release

    def rollback(self, profile_id: str, target_version_id: str, *, actor_id: str) -> PersonaRelease:
        target = self._get_version(target_version_id)
        if target.profile_id != profile_id:
            raise PersonaManagementError("rollback_profile_mismatch")
        if not any(
            release.version_id == target_version_id
            for release in self._repository.list_releases(profile_id)
        ):
            raise PersonaManagementError("rollback_target_not_released")
        active = self._active_release(profile_id)
        if active and active.version_id == target_version_id:
            return active
        if active:
            self._repository.save_release(replace(active, status=ReleaseStatus.ROLLED_BACK))
        release = PersonaRelease(
            release_id=uuid4().hex,
            version_id=target_version_id,
            status=ReleaseStatus.ACTIVE,
            actor_id=actor_id,
            replaced_release_id=active.release_id if active else None,
            rollback_of_release_id=active.release_id if active else None,
        )
        self._repository.save_release(release)
        self._repository.set_active_release(profile_id, release.release_id)
        return release

    def archive(self, release_id: str) -> PersonaRelease:
        try:
            release = self._repository.get_release(release_id)
            if release is None:
                raise KeyError(release_id)
        except KeyError as exc:
            raise PersonaManagementError("release_not_found") from exc
        if release.status == ReleaseStatus.ARCHIVED:
            return release
        if release.status == ReleaseStatus.ACTIVE:
            raise PersonaManagementError("active_release_cannot_be_archived")
        archived = replace(release, status=ReleaseStatus.ARCHIVED)
        self._repository.save_release(archived)
        return archived

    def save_binding(self, binding: PersonaBinding) -> PersonaBinding:
        version = self._repository.get_version(binding.version_id)
        if version is None:
            raise PersonaManagementError("binding_version_not_found")
        active = self._active_release(version.profile_id)
        if active is None or active.version_id != binding.version_id:
            raise PersonaManagementError("binding_version_not_active")
        scope_key = binding.scope_key.strip()
        if binding.scope == BindingScope.GLOBAL:
            if scope_key != "*":
                raise PersonaManagementError("global_binding_key_must_be_wildcard")
        elif not scope_key:
            raise PersonaManagementError("binding_scope_key_required")
        if any(key.strip().lower() == "profile_id" for key, _ in binding.surface):
            raise PersonaManagementError("surface_cannot_override_profile_id")
        self._repository.save_binding(binding)
        return binding

    def list_bindings(self) -> tuple[PersonaBinding, ...]:
        return self._repository.list_bindings()

    def get_version(self, version_id: str) -> PersonaVersion:
        return self._get_version(version_id)

    def get_runtime_projection(
        self,
        profile_id: str,
        context: BindingContext,
    ) -> PersonaRuntimeProjection:
        active_version = self.get_active_version(profile_id)
        if active_version is None:
            raise PersonaManagementError("active_version_not_found")
        binding = resolve_binding(self.list_bindings(), context)
        if binding is not None and binding.version_id != active_version.version_id:
            binding = None
        return build_runtime_projection(active_version, binding)

    def get_status(self) -> PersonaManagementStatus:
        versions = self._repository.list_all_versions()
        releases = self._repository.list_all_releases()
        active_profiles = tuple(
            sorted(
                {
                    version.profile_id
                    for version in versions
                    if (active := self._repository.get_active_release(version.profile_id))
                    and active.version_id == version.version_id
                }
            )
        )
        return PersonaManagementStatus(
            storage_backend=self._repository.backend_name,
            durable=self._repository.durable,
            write_ready=self._repository.durable,
            draft_count=len(self._repository.list_drafts()),
            version_count=len(versions),
            release_count=len(releases),
            binding_count=len(self._repository.list_bindings()),
            active_profiles=active_profiles,
        )

    def get_active_version(self, profile_id: str) -> PersonaVersion | None:
        release = self._active_release(profile_id)
        return self._repository.get_version(release.version_id) if release else None

    def list_versions(self, profile_id: str) -> tuple[PersonaVersion, ...]:
        return self._repository.list_versions(profile_id)

    def list_releases(self, profile_id: str) -> tuple[PersonaRelease, ...]:
        return self._repository.list_releases(profile_id)

    def _get_draft(self, draft_id: str) -> PersonaDraft:
        try:
            draft = self._repository.get_draft(draft_id)
            if draft is None:
                raise KeyError(draft_id)
            return draft
        except KeyError as exc:
            raise PersonaManagementError("draft_not_found") from exc

    def _get_version(self, version_id: str) -> PersonaVersion:
        try:
            version = self._repository.get_version(version_id)
            if version is None:
                raise KeyError(version_id)
            return version
        except KeyError as exc:
            raise PersonaManagementError("version_not_found") from exc

    def _set_draft_status(self, draft_id: str, status: DraftStatus) -> PersonaDraft:
        draft = replace(self._get_draft(draft_id), status=status)
        self._repository.save_draft(draft)
        return draft

    def _version_for_draft(self, draft_id: str) -> PersonaVersion:
        version = self._repository.find_version_by_draft(draft_id)
        if version is None:
            raise PersonaManagementError("version_not_found")
        return version

    def _active_release(self, profile_id: str) -> PersonaRelease | None:
        return self._repository.get_active_release(profile_id)
