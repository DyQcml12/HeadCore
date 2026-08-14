from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, TypeVar

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.database_control.actor import (
    build_actor_identity,
    require_actor,
    require_mutate_admin,
    require_read_admin,
)
from app.database_control.contracts import ActorIdentity, DatabaseActor, DatabaseStatus
from app.database_control.errors import DatabaseControlError, DatabaseNotReadyError
from app.database_control.persona_audit import PersonaControlAuditSink
from app.persona_management.contracts import (
    BindingContext,
    BindingScope,
    PersonaBinding,
    PersonaDefinition,
    PersonaManagementStatus,
    PersonaRelease,
    PersonaRuntimeProjection,
    PersonaValidationResult,
    ValidationStage,
)
from app.persona_management.interfaces import AsyncPersonaManagementService
from app.persona_management.router import PersonaVersionSummary, version_summary
from app.persona_management.service import PersonaManagementError


T = TypeVar("T")


class PersonaAsyncActorResolver(Protocol):
    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None: ...


class PersonaReadinessProvider(Protocol):
    async def get_status(self) -> object: ...


class PersonaDefinitionInput(BaseModel):
    profile_id: str = Field(min_length=1, max_length=64)
    aliases: list[str] = Field(min_length=1, max_length=32)
    default_style: str = Field(min_length=1, max_length=1000)
    core_lines: list[str] = Field(min_length=1, max_length=100)
    enabled_gates: list[str] = Field(min_length=1, max_length=100)

    def to_domain(self) -> PersonaDefinition:
        return PersonaDefinition(
            profile_id=self.profile_id,
            aliases=tuple(self.aliases),
            default_style=self.default_style,
            core_lines=tuple(self.core_lines),
            enabled_gates=frozenset(self.enabled_gates),
        )


class PersonaDraftCreateRequest(BaseModel):
    definition: PersonaDefinitionInput
    draft_id: str | None = Field(default=None, min_length=1, max_length=128)


class PersonaDraftSummary(BaseModel):
    draft_id: str
    profile_id: str
    status: str
    created_by: str
    created_at: str


class PersonaEvaluationRequest(BaseModel):
    stage: Literal["regression", "live_acceptance"]
    passed: bool
    errors: list[str] = Field(default_factory=list, max_length=100)


class PersonaOperationRequest(BaseModel):
    operation_id: str = Field(min_length=1, max_length=128)


class PersonaRollbackRequest(PersonaOperationRequest):
    target_version_id: str = Field(min_length=1, max_length=128)


class PersonaBindingWriteRequest(BaseModel):
    binding_id: str = Field(min_length=1, max_length=128)
    scope: BindingScope
    scope_key: str = Field(min_length=1, max_length=255)
    version_id: str = Field(min_length=1, max_length=128)
    surface: dict[str, str] = Field(default_factory=dict, max_length=50)
    active: bool = True

    def to_domain(self) -> PersonaBinding:
        return PersonaBinding(
            binding_id=self.binding_id,
            scope=self.scope,
            scope_key=self.scope_key,
            version_id=self.version_id,
            surface=tuple(sorted(self.surface.items())),
            active=self.active,
        )


def _draft_summary(draft) -> PersonaDraftSummary:  # type: ignore[no-untyped-def]
    return PersonaDraftSummary(
        draft_id=draft.draft_id,
        profile_id=draft.definition.profile_id,
        status=draft.status,
        created_by=draft.created_by,
        created_at=draft.created_at.isoformat(),
    )


def create_async_persona_management_router(
    service: AsyncPersonaManagementService,
    actor_resolver: PersonaAsyncActorResolver,
    *,
    readiness_provider: PersonaReadinessProvider | None = None,
    audit_sink: PersonaControlAuditSink | None = None,
    enable_writes: bool = False,
) -> APIRouter:
    router = APIRouter(prefix="/api/control/personas-v2", tags=["persona-management-v2"])

    async def actor_from_headers(
        platform: str | None, user_id: str | None, group_id: str | None
    ) -> DatabaseActor:
        identity = build_actor_identity(
            platform=platform,
            platform_user_id=user_id,
            platform_group_id=group_id,
        )
        return require_actor(await actor_resolver.resolve_actor(identity))

    async def authorize_read(
        platform: str | None, user_id: str | None, group_id: str | None
    ) -> DatabaseActor:
        actor = await actor_from_headers(platform, user_id, group_id)
        require_read_admin(actor)
        return actor

    async def require_write_ready(actor: DatabaseActor) -> None:
        require_mutate_admin(actor)
        if not enable_writes or readiness_provider is None or audit_sink is None:
            raise DatabaseNotReadyError("persona management writes are disabled")
        persona_status = await service.get_status()
        if not persona_status.durable:
            raise DatabaseNotReadyError("persona management storage is not durable")
        status = await readiness_provider.get_status()
        if not _readiness_ready(status):
            raise DatabaseNotReadyError("Database V2 is not ready for persona writes")

    async def audited_write(
        *,
        operation: str,
        target_type: str,
        target_id: str,
        platform: str | None,
        user_id: str | None,
        group_id: str | None,
        action: Callable[[DatabaseActor], Awaitable[T]],
    ) -> T:
        try:
            actor = await actor_from_headers(platform, user_id, group_id)
        except DatabaseControlError:
            raise
        try:
            await require_write_ready(actor)
            result = await action(actor)
        except (DatabaseControlError, PersonaManagementError) as exc:
            if audit_sink is not None:
                reason_code = exc.code if isinstance(exc, DatabaseControlError) else str(exc)
                await audit_sink.record(
                    actor_profile_id=actor.profile_id,
                    operation=operation,
                    target_type=target_type,
                    target_id=target_id,
                    status="rejected",
                    reason_code=reason_code,
                )
            raise
        except Exception as exc:
            if audit_sink is not None:
                await audit_sink.record(
                    actor_profile_id=actor.profile_id,
                    operation=operation,
                    target_type=target_type,
                    target_id=target_id,
                    status="failed",
                    reason_code=type(exc).__name__,
                )
            raise
        assert audit_sink is not None
        await audit_sink.record(
            actor_profile_id=actor.profile_id,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            status="accepted",
            reason_code="completed",
        )
        return result

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

    def headers(
        platform: str | None, user_id: str | None, group_id: str | None
    ) -> tuple[str | None, str | None, str | None]:
        return platform, user_id, group_id

    @router.get("/status", response_model=PersonaManagementStatus)
    async def status(
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            await authorize_read(*headers(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id))
            result = await service.get_status()
            ready = False
            if enable_writes and result.durable and readiness_provider is not None:
                database_status = await readiness_provider.get_status()
                ready = _readiness_ready(database_status)
            return PersonaManagementStatus(**{**result.__dict__, "write_ready": ready})

        return await call(operation)

    @router.get("/drafts/{draft_id}", response_model=PersonaDraftSummary)
    async def draft_detail(
        draft_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            await authorize_read(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            return _draft_summary(await service.get_draft(draft_id))

        return await call(operation)

    @router.get(
        "/drafts/{draft_id}/validations", response_model=list[PersonaValidationResult]
    )
    async def validations(
        draft_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            await authorize_read(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            return list(await service.list_validations(draft_id))

        return await call(operation)

    @router.get("/{profile_id}/versions", response_model=list[PersonaVersionSummary])
    async def versions(profile_id: str, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            await authorize_read(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            return [version_summary(item) for item in await service.list_versions(profile_id)]
        return await call(operation)

    @router.get("/{profile_id}/releases", response_model=list[PersonaRelease])
    async def releases(profile_id: str, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            await authorize_read(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            return list(await service.list_releases(profile_id))
        return await call(operation)

    @router.get("/bindings/all", response_model=list[PersonaBinding])
    async def bindings(x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            await authorize_read(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            return list(await service.list_bindings())
        return await call(operation)

    @router.get("/{profile_id}/runtime-projection", response_model=PersonaRuntimeProjection)
    async def projection(profile_id: str, platform: str = Query(default="", max_length=32), relationship: str = Query(default="", max_length=64), subject_profile_id: str = Query(default="", max_length=128), conversation_id: str = Query(default="", max_length=128), x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            await authorize_read(x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id)
            return await service.get_runtime_projection(profile_id, BindingContext(platform, relationship, subject_profile_id, conversation_id))
        return await call(operation)

    @router.post("/drafts", response_model=PersonaDraftSummary)
    async def create_draft(payload: PersonaDraftCreateRequest, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            async def action(actor: DatabaseActor):
                return _draft_summary(await service.create_draft(payload.definition.to_domain(), actor_id=actor.profile_id, draft_id=payload.draft_id))
            return await audited_write(operation="create_draft", target_type="draft", target_id=payload.draft_id or "generated", platform=x_hutao_actor_platform, user_id=x_hutao_actor_user_id, group_id=x_hutao_actor_group_id, action=action)
        return await call(operation)

    @router.post("/drafts/{draft_id}/validate", response_model=list[PersonaValidationResult])
    async def validate(draft_id: str, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            async def action(_actor: DatabaseActor):
                return list(await service.validate_draft(draft_id))
            return await audited_write(operation="validate_draft", target_type="draft", target_id=draft_id, platform=x_hutao_actor_platform, user_id=x_hutao_actor_user_id, group_id=x_hutao_actor_group_id, action=action)
        return await call(operation)

    @router.post("/drafts/{draft_id}/evaluations", response_model=PersonaDraftSummary)
    async def evaluate(draft_id: str, payload: PersonaEvaluationRequest, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            async def action(_actor: DatabaseActor):
                result = PersonaValidationResult(stage=ValidationStage(payload.stage), passed=payload.passed, errors=tuple(payload.errors))
                return _draft_summary(await service.record_evaluation(draft_id, result))
            return await audited_write(operation="record_evaluation", target_type="draft", target_id=draft_id, platform=x_hutao_actor_platform, user_id=x_hutao_actor_user_id, group_id=x_hutao_actor_group_id, action=action)
        return await call(operation)

    @router.post("/drafts/{draft_id}/approve", response_model=PersonaVersionSummary)
    async def approve(draft_id: str, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            async def action(actor: DatabaseActor):
                return version_summary(await service.approve(draft_id, actor_id=actor.profile_id))
            return await audited_write(operation="approve_draft", target_type="draft", target_id=draft_id, platform=x_hutao_actor_platform, user_id=x_hutao_actor_user_id, group_id=x_hutao_actor_group_id, action=action)
        return await call(operation)

    @router.post("/versions/{version_id}/publish", response_model=PersonaRelease)
    async def publish(version_id: str, payload: PersonaOperationRequest, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            async def action(actor: DatabaseActor):
                return await service.publish(version_id, actor_id=actor.profile_id, operation_id=payload.operation_id)
            return await audited_write(operation="publish_version", target_type="version", target_id=version_id, platform=x_hutao_actor_platform, user_id=x_hutao_actor_user_id, group_id=x_hutao_actor_group_id, action=action)
        return await call(operation)

    @router.post("/{profile_id}/rollback", response_model=PersonaRelease)
    async def rollback(profile_id: str, payload: PersonaRollbackRequest, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            async def action(actor: DatabaseActor):
                return await service.rollback(profile_id, payload.target_version_id, actor_id=actor.profile_id, operation_id=payload.operation_id)
            return await audited_write(operation="rollback_version", target_type="profile", target_id=profile_id, platform=x_hutao_actor_platform, user_id=x_hutao_actor_user_id, group_id=x_hutao_actor_group_id, action=action)
        return await call(operation)

    @router.put("/bindings/{binding_id}", response_model=PersonaBinding)
    async def save_binding(binding_id: str, payload: PersonaBindingWriteRequest, x_hutao_actor_platform: str | None = Header(default=None), x_hutao_actor_user_id: str | None = Header(default=None), x_hutao_actor_group_id: str | None = Header(default=None)):
        async def operation():
            async def action(actor: DatabaseActor):
                if binding_id != payload.binding_id:
                    raise PersonaManagementError("binding_id_mismatch")
                return await service.save_binding(payload.to_domain(), actor_id=actor.profile_id)
            return await audited_write(operation="save_binding", target_type="binding", target_id=binding_id, platform=x_hutao_actor_platform, user_id=x_hutao_actor_user_id, group_id=x_hutao_actor_group_id, action=action)
        return await call(operation)

    return router


def _readiness_ready(status: object) -> bool:
    write_ready = getattr(status, "write_ready", None)
    if write_ready is not None:
        return bool(write_ready)
    return bool(
        getattr(status, "ready", False)
        and getattr(status, "database_v2_enabled", False)
    )
