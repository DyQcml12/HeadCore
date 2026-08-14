from __future__ import annotations

from typing import Protocol

from app.persona_management.contracts import (
    BindingContext,
    PersonaBinding,
    PersonaDefinition,
    PersonaDraft,
    PersonaManagementStatus,
    PersonaRelease,
    PersonaRuntimeProjection,
    PersonaValidationResult,
    PersonaVersion,
)


class AsyncPersonaManagementService(Protocol):
    async def get_status(self) -> PersonaManagementStatus: ...

    async def get_draft(self, draft_id: str) -> PersonaDraft: ...

    async def list_validations(
        self, draft_id: str
    ) -> tuple[PersonaValidationResult, ...]: ...

    async def list_versions(self, profile_id: str) -> tuple[PersonaVersion, ...]: ...

    async def list_releases(self, profile_id: str) -> tuple[PersonaRelease, ...]: ...

    async def get_version(self, version_id: str) -> PersonaVersion: ...

    async def list_bindings(self) -> tuple[PersonaBinding, ...]: ...

    async def get_runtime_projection(
        self, profile_id: str, context: BindingContext
    ) -> PersonaRuntimeProjection: ...

    async def create_draft(
        self, definition: PersonaDefinition, *, actor_id: str, draft_id: str | None = None
    ) -> PersonaDraft: ...

    async def validate_draft(
        self, draft_id: str
    ) -> tuple[PersonaValidationResult, ...]: ...

    async def record_evaluation(
        self, draft_id: str, result: PersonaValidationResult
    ) -> PersonaDraft: ...

    async def approve(self, draft_id: str, *, actor_id: str) -> PersonaVersion: ...

    async def publish(
        self, version_id: str, *, actor_id: str, operation_id: str
    ) -> PersonaRelease: ...

    async def rollback(
        self,
        profile_id: str,
        target_version_id: str,
        *,
        actor_id: str,
        operation_id: str,
    ) -> PersonaRelease: ...

    async def save_binding(
        self, binding: PersonaBinding, *, actor_id: str
    ) -> PersonaBinding: ...

