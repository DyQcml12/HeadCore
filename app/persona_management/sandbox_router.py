from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.persona_management.sandbox import (
    LocalSandboxPersonaService,
    SandboxPersona,
    SandboxPersonaError,
    SandboxPersonaNotFoundError,
)


class SandboxPersonaWriteRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    traits: list[str] = Field(default_factory=list, max_length=3)
    detail: str = Field(default="", max_length=6000)
    model_label: str | None = Field(default=None, max_length=255)


class SandboxPersonaResponse(BaseModel):
    persona_id: str
    name: str
    traits: list[str]
    detail: str
    model_label: str | None
    created_at: str
    updated_at: str


SandboxOwnerResolver = Callable[[str, str | None, str | None, str | None, bool], Awaitable[str]]


def create_sandbox_persona_router(
    service: LocalSandboxPersonaService,
    owner_resolver: SandboxOwnerResolver,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/sandbox/personas", tags=["sandbox-personas"])

    async def resolve_owner(
        user_id: str,
        hutao_session: str | None,
        csrf_token: str | None,
        authorization: str | None,
        *,
        require_csrf: bool,
    ) -> str:
        return await owner_resolver(
            user_id,
            hutao_session,
            csrf_token,
            authorization,
            require_csrf,
        )

    def response(persona: SandboxPersona) -> SandboxPersonaResponse:
        return SandboxPersonaResponse(
            persona_id=persona.persona_id,
            name=persona.name,
            traits=list(persona.traits),
            detail=persona.detail,
            model_label=persona.model_label,
            created_at=persona.created_at,
            updated_at=persona.updated_at,
        )

    def raise_service_error(error: SandboxPersonaError) -> None:
        code = str(error)
        response_status = (
            status.HTTP_404_NOT_FOUND
            if isinstance(error, SandboxPersonaNotFoundError)
            else status.HTTP_503_SERVICE_UNAVAILABLE
            if code == "sandbox_persona_storage_unavailable"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=response_status, detail=code) from error

    @router.get("", response_model=list[SandboxPersonaResponse])
    async def list_personas(
        user_id: str = Query(min_length=1, max_length=128),
        hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
        authorization: str | None = Header(default=None),
    ) -> list[SandboxPersonaResponse]:
        owner_id = await resolve_owner(user_id, hutao_session, None, authorization, require_csrf=False)
        try:
            personas = await service.list_for_owner(owner_id)
        except SandboxPersonaError as error:
            raise_service_error(error)
        return [response(persona) for persona in personas]

    @router.post("", response_model=SandboxPersonaResponse, status_code=status.HTTP_201_CREATED)
    async def create_persona(
        request: SandboxPersonaWriteRequest,
        hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        authorization: str | None = Header(default=None),
    ) -> SandboxPersonaResponse:
        owner_id = await resolve_owner(
            request.user_id, hutao_session, csrf_token, authorization, require_csrf=True
        )
        try:
            persona = await service.create(
                owner_id=owner_id,
                name=request.name,
                traits=tuple(request.traits),
                detail=request.detail,
                model_label=request.model_label,
            )
        except SandboxPersonaError as error:
            raise_service_error(error)
        return response(persona)

    @router.get("/{persona_id}", response_model=SandboxPersonaResponse)
    async def get_persona(
        persona_id: str,
        user_id: str = Query(min_length=1, max_length=128),
        hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
        authorization: str | None = Header(default=None),
    ) -> SandboxPersonaResponse:
        owner_id = await resolve_owner(user_id, hutao_session, None, authorization, require_csrf=False)
        try:
            persona = await service.get_for_owner(persona_id, owner_id=owner_id)
        except SandboxPersonaError as error:
            raise_service_error(error)
        return response(persona)

    @router.put("/{persona_id}", response_model=SandboxPersonaResponse)
    async def replace_persona(
        persona_id: str,
        request: SandboxPersonaWriteRequest,
        hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        authorization: str | None = Header(default=None),
    ) -> SandboxPersonaResponse:
        owner_id = await resolve_owner(
            request.user_id, hutao_session, csrf_token, authorization, require_csrf=True
        )
        try:
            persona = await service.replace(
                persona_id,
                owner_id=owner_id,
                name=request.name,
                traits=tuple(request.traits),
                detail=request.detail,
                model_label=request.model_label,
            )
        except SandboxPersonaError as error:
            raise_service_error(error)
        return response(persona)

    @router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_persona(
        persona_id: str,
        user_id: str = Query(min_length=1, max_length=128),
        hutao_session: str | None = Cookie(default=None, alias="hutao_session"),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        authorization: str | None = Header(default=None),
    ) -> None:
        owner_id = await resolve_owner(
            user_id, hutao_session, csrf_token, authorization, require_csrf=True
        )
        try:
            await service.delete(persona_id, owner_id=owner_id)
        except SandboxPersonaError as error:
            raise_service_error(error)

    return router
