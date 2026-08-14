from __future__ import annotations

from typing import Protocol

from app.persona_management.contracts import (
    PersonaBinding,
    PersonaDraft,
    PersonaRelease,
    PersonaValidationResult,
    PersonaVersion,
    ValidationStage,
)


class PersonaManagementRepository(Protocol):
    @property
    def backend_name(self) -> str: ...

    @property
    def durable(self) -> bool: ...

    def get_draft(self, draft_id: str) -> PersonaDraft | None: ...

    def save_draft(self, draft: PersonaDraft) -> None: ...

    def list_drafts(self) -> tuple[PersonaDraft, ...]: ...

    def get_validations(self, draft_id: str) -> dict[ValidationStage, PersonaValidationResult]: ...

    def save_validation(self, draft_id: str, result: PersonaValidationResult) -> None: ...

    def get_version(self, version_id: str) -> PersonaVersion | None: ...

    def save_version(self, version: PersonaVersion) -> None: ...

    def list_versions(self, profile_id: str) -> tuple[PersonaVersion, ...]: ...

    def list_all_versions(self) -> tuple[PersonaVersion, ...]: ...

    def find_version_by_draft(self, draft_id: str) -> PersonaVersion | None: ...

    def get_release(self, release_id: str) -> PersonaRelease | None: ...

    def save_release(self, release: PersonaRelease) -> None: ...

    def get_active_release(self, profile_id: str) -> PersonaRelease | None: ...

    def set_active_release(self, profile_id: str, release_id: str) -> None: ...

    def list_releases(self, profile_id: str) -> tuple[PersonaRelease, ...]: ...

    def list_all_releases(self) -> tuple[PersonaRelease, ...]: ...

    def save_binding(self, binding: PersonaBinding) -> None: ...

    def list_bindings(self) -> tuple[PersonaBinding, ...]: ...


class InMemoryPersonaManagementRepository:
    def __init__(self) -> None:
        self._drafts: dict[str, PersonaDraft] = {}
        self._validations: dict[str, dict[ValidationStage, PersonaValidationResult]] = {}
        self._versions: dict[str, PersonaVersion] = {}
        self._releases: dict[str, PersonaRelease] = {}
        self._active_release_by_profile: dict[str, str] = {}
        self._bindings: dict[str, PersonaBinding] = {}

    @property
    def backend_name(self) -> str:
        return "memory"

    @property
    def durable(self) -> bool:
        return False

    def get_draft(self, draft_id: str) -> PersonaDraft | None:
        return self._drafts.get(draft_id)

    def save_draft(self, draft: PersonaDraft) -> None:
        self._drafts[draft.draft_id] = draft
        self._validations.setdefault(draft.draft_id, {})

    def list_drafts(self) -> tuple[PersonaDraft, ...]:
        return tuple(self._drafts.values())

    def get_validations(self, draft_id: str) -> dict[ValidationStage, PersonaValidationResult]:
        return dict(self._validations.get(draft_id, {}))

    def save_validation(self, draft_id: str, result: PersonaValidationResult) -> None:
        self._validations.setdefault(draft_id, {})[result.stage] = result

    def get_version(self, version_id: str) -> PersonaVersion | None:
        return self._versions.get(version_id)

    def save_version(self, version: PersonaVersion) -> None:
        self._versions[version.version_id] = version

    def list_versions(self, profile_id: str) -> tuple[PersonaVersion, ...]:
        return tuple(
            sorted(
                (version for version in self._versions.values() if version.profile_id == profile_id),
                key=lambda version: version.version,
            )
        )

    def list_all_versions(self) -> tuple[PersonaVersion, ...]:
        return tuple(sorted(self._versions.values(), key=lambda version: version.version_id))

    def find_version_by_draft(self, draft_id: str) -> PersonaVersion | None:
        return next(
            (version for version in self._versions.values() if version.source_draft_id == draft_id),
            None,
        )

    def get_release(self, release_id: str) -> PersonaRelease | None:
        return self._releases.get(release_id)

    def save_release(self, release: PersonaRelease) -> None:
        self._releases[release.release_id] = release

    def get_active_release(self, profile_id: str) -> PersonaRelease | None:
        release_id = self._active_release_by_profile.get(profile_id)
        return self._releases.get(release_id) if release_id else None

    def set_active_release(self, profile_id: str, release_id: str) -> None:
        self._active_release_by_profile[profile_id] = release_id

    def list_releases(self, profile_id: str) -> tuple[PersonaRelease, ...]:
        version_ids = {version.version_id for version in self.list_versions(profile_id)}
        return tuple(release for release in self._releases.values() if release.version_id in version_ids)

    def list_all_releases(self) -> tuple[PersonaRelease, ...]:
        return tuple(self._releases.values())

    def save_binding(self, binding: PersonaBinding) -> None:
        self._bindings[binding.binding_id] = binding

    def list_bindings(self) -> tuple[PersonaBinding, ...]:
        return tuple(self._bindings.values())
