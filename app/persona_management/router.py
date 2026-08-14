from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database_control.actor import build_actor_identity, require_read_admin
from app.database_control.contracts import ActorIdentity, DatabaseActor
from app.database_control.errors import DatabaseControlError
from app.persona_management.contracts import (
    BindingContext,
    PersonaBinding,
    PersonaManagementStatus,
    PersonaRelease,
    PersonaRuntimeProjection,
    PersonaVersion,
)
from app.persona_management.service import (
    InMemoryPersonaManagementService,
    PersonaManagementError,
)


class PersonaActorResolver(Protocol):
    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None: ...


class PersonaVersionSummary(BaseModel):
    profile_id: str
    version: int
    version_id: str
    source_draft_id: str
    approved_by: str
    default_style: str
    created_at: str


def version_summary(version: PersonaVersion) -> PersonaVersionSummary:
    return PersonaVersionSummary(
        profile_id=version.profile_id,
        version=version.version,
        version_id=version.version_id,
        source_draft_id=version.source_draft_id,
        approved_by=version.approved_by,
        default_style=version.definition.default_style,
        created_at=version.created_at.isoformat(),
    )


def create_persona_management_router(
    service: InMemoryPersonaManagementService,
    actor_resolver: PersonaActorResolver,
) -> APIRouter:
    router = APIRouter(prefix="/api/control/personas", tags=["persona-management"])

    async def authorize(
        platform: str | None,
        user_id: str | None,
        group_id: str | None,
    ) -> None:
        identity = build_actor_identity(
            platform=platform,
            platform_user_id=user_id,
            platform_group_id=group_id,
        )
        actor = await actor_resolver.resolve_actor(identity)
        if actor is None:
            from app.database_control.errors import UnauthenticatedError

            raise UnauthenticatedError("persona management actor could not be resolved")
        require_read_admin(actor)

    async def call(operation):  # type: ignore[no-untyped-def]
        try:
            return await operation()
        except DatabaseControlError as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.response())
        except PersonaManagementError as exc:
            code = str(exc)
            status_code = 404 if code.endswith("not_found") else 409
            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": code}},
            )

    async def authorized_call(
        operation,  # type: ignore[no-untyped-def]
        platform: str | None,
        user_id: str | None,
        group_id: str | None,
    ):
        async def execute():
            await authorize(platform, user_id, group_id)
            return operation()

        return await call(execute)

    @router.get("/status", response_model=PersonaManagementStatus)
    async def status(
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        return await authorized_call(
            service.get_status,
            x_hutao_actor_platform,
            x_hutao_actor_user_id,
            x_hutao_actor_group_id,
        )

    @router.get("/{profile_id}/versions", response_model=list[PersonaVersionSummary])
    async def versions(
        profile_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        return await authorized_call(
            lambda: [version_summary(version) for version in service.list_versions(profile_id)],
            x_hutao_actor_platform,
            x_hutao_actor_user_id,
            x_hutao_actor_group_id,
        )

    @router.get("/{profile_id}/releases", response_model=list[PersonaRelease])
    async def releases(
        profile_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        return await authorized_call(
            lambda: list(service.list_releases(profile_id)),
            x_hutao_actor_platform,
            x_hutao_actor_user_id,
            x_hutao_actor_group_id,
        )

    @router.get("/versions/{version_id}", response_model=PersonaVersionSummary)
    async def version_detail(
        version_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        return await authorized_call(
            lambda: version_summary(service.get_version(version_id)),
            x_hutao_actor_platform,
            x_hutao_actor_user_id,
            x_hutao_actor_group_id,
        )

    @router.get("/bindings/all", response_model=list[PersonaBinding])
    async def bindings(
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        return await authorized_call(
            lambda: list(service.list_bindings()),
            x_hutao_actor_platform,
            x_hutao_actor_user_id,
            x_hutao_actor_group_id,
        )

    @router.get("/{profile_id}/runtime-projection", response_model=PersonaRuntimeProjection)
    async def runtime_projection(
        profile_id: str,
        platform: str = Query(default="", max_length=32),
        relationship: str = Query(default="", max_length=64),
        subject_profile_id: str = Query(default="", max_length=128),
        conversation_id: str = Query(default="", max_length=128),
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        context = BindingContext(
            platform=platform,
            relationship=relationship,
            profile_id=subject_profile_id,
            conversation_id=conversation_id,
        )
        return await authorized_call(
            lambda: service.get_runtime_projection(profile_id, context),
            x_hutao_actor_platform,
            x_hutao_actor_user_id,
            x_hutao_actor_group_id,
        )

    return router
