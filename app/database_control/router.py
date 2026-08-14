from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from app.database_control.actor import build_actor_identity
from app.database_control.contracts import (
    AdminProfileResponse,
    BindAccountsRequest,
    BindAccountsResponse,
    BootstrapAdminRequest,
    BootstrapAdminResponse,
    ClaimReviewResponse,
    DatabaseStatus,
    ProfileDetail,
    ProfileFilters,
    ProfilePage,
    RelationshipType,
    RelationshipUpdateRequest,
    RelationshipUpdateResponse,
)
from app.database_control.errors import DatabaseControlError, translate_database_exception
from app.database_control.service import DatabaseControlService


def create_database_control_router(service: DatabaseControlService) -> APIRouter:
    router = APIRouter(prefix="/api/control/database-v2", tags=["database-v2-control"])

    async def call(operation):  # type: ignore[no-untyped-def]
        try:
            return await operation()
        except DatabaseControlError as exc:
            return JSONResponse(status_code=exc.status_code, content=exc.response())
        except Exception as exc:
            translated = translate_database_exception(exc)
            if translated is None:
                raise
            return JSONResponse(
                status_code=translated.status_code,
                content=translated.response(),
            )

    async def actor_from_headers(
        platform: str | None,
        user_id: str | None,
        group_id: str | None,
    ):
        identity = build_actor_identity(
            platform=platform,
            platform_user_id=user_id,
            platform_group_id=group_id,
        )
        return await service.resolve_read_actor(identity)

    @router.get("/status", response_model=DatabaseStatus)
    async def status(
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            actor = await actor_from_headers(
                x_hutao_actor_platform,
                x_hutao_actor_user_id,
                x_hutao_actor_group_id,
            )
            return await service.get_status(actor)

        return await call(operation)

    @router.get("/admin", response_model=AdminProfileResponse)
    async def admin(
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            actor = await actor_from_headers(
                x_hutao_actor_platform,
                x_hutao_actor_user_id,
                x_hutao_actor_group_id,
            )
            return await service.get_admin(actor)

        return await call(operation)

    @router.get("/profiles", response_model=ProfilePage)
    async def profiles(
        relationship_type: RelationshipType | None = Query(default=None),
        verified: bool | None = Query(default=None),
        platform: Literal["qq", "wechat"] | None = Query(default=None),
        q: str = Query(default="", max_length=100),
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=500),
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            actor = await actor_from_headers(
                x_hutao_actor_platform,
                x_hutao_actor_user_id,
                x_hutao_actor_group_id,
            )
            filters = ProfileFilters(
                relationship_type=relationship_type,
                verified=verified,
                platform=platform,
                query=q,
            )
            return await service.list_profiles(
                actor,
                filters=filters,
                limit=limit,
                cursor=cursor,
            )

        return await call(operation)

    @router.get("/profiles/{profile_id}", response_model=ProfileDetail)
    async def profile_detail(
        profile_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            actor = await actor_from_headers(
                x_hutao_actor_platform,
                x_hutao_actor_user_id,
                x_hutao_actor_group_id,
            )
            return await service.get_profile(actor, profile_id)

        return await call(operation)

    @router.post("/bootstrap-admin", response_model=BootstrapAdminResponse)
    async def bootstrap_admin(payload: BootstrapAdminRequest, request: Request):
        async def operation():
            host = request.client.host if request.client is not None else ""
            return await service.bootstrap_admin(
                payload,
                local_request=host in {"127.0.0.1", "::1", "testclient"},
            )

        return await call(operation)

    @router.post(
        "/profiles/{profile_id}/relationship",
        response_model=RelationshipUpdateResponse,
    )
    async def set_profile_relationship(
        profile_id: str,
        payload: RelationshipUpdateRequest,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            actor = await actor_from_headers(
                x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id
            )
            return await service.set_profile_relationship(actor, profile_id, payload)

        return await call(operation)

    @router.post("/platform-accounts/bind", response_model=BindAccountsResponse)
    async def bind_accounts(
        payload: BindAccountsRequest,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        async def operation():
            actor = await actor_from_headers(
                x_hutao_actor_platform, x_hutao_actor_user_id, x_hutao_actor_group_id
            )
            return await service.bind_accounts(actor, payload)

        return await call(operation)

    async def review_claim(
        claim_id: str,
        approve: bool,
        platform: str | None,
        user_id: str | None,
        group_id: str | None,
    ):
        actor = await actor_from_headers(platform, user_id, group_id)
        return await service.review_claim(actor, claim_id, approve=approve)

    @router.post("/claims/{claim_id}/approve", response_model=ClaimReviewResponse)
    async def approve_claim(
        claim_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        return await call(
            lambda: review_claim(
                claim_id,
                True,
                x_hutao_actor_platform,
                x_hutao_actor_user_id,
                x_hutao_actor_group_id,
            )
        )

    @router.post("/claims/{claim_id}/reject", response_model=ClaimReviewResponse)
    async def reject_claim(
        claim_id: str,
        x_hutao_actor_platform: str | None = Header(default=None),
        x_hutao_actor_user_id: str | None = Header(default=None),
        x_hutao_actor_group_id: str | None = Header(default=None),
    ):
        return await call(
            lambda: review_claim(
                claim_id,
                False,
                x_hutao_actor_platform,
                x_hutao_actor_user_id,
                x_hutao_actor_group_id,
            )
        )

    return router
