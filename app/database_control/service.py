from __future__ import annotations

from typing import Protocol

from app.database_control.actor import require_actor, require_mutate_admin, require_read_admin
from app.database_control.contracts import (
    ActorIdentity,
    AdminProfileResponse,
    BindAccountsRequest,
    BindAccountsResponse,
    BootstrapAdminRequest,
    BootstrapAdminResponse,
    ClaimReviewResponse,
    DatabaseActor,
    DatabaseStatus,
    ControlAuditEvent,
    ProfileDetail,
    ProfileFilters,
    ProfilePage,
    RelationshipUpdateRequest,
    RelationshipUpdateResponse,
    sanitized_account,
)
from app.database_control.errors import DatabaseNotReadyError, ForbiddenError, ResourceNotFoundError


class DatabaseControlRepository(Protocol):
    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None: ...

    async def get_status(self) -> DatabaseStatus: ...

    async def get_admin_profile(self) -> AdminProfileResponse | None: ...

    async def list_profiles(
        self,
        *,
        filters: ProfileFilters,
        limit: int,
        cursor: str | None,
    ) -> ProfilePage: ...

    async def get_profile(self, profile_id: str) -> ProfileDetail | None: ...

    async def bootstrap_admin(
        self,
        request: BootstrapAdminRequest,
        *,
        local_request: bool,
    ) -> BootstrapAdminResponse: ...

    async def set_profile_relationship(
        self,
        *,
        actor: DatabaseActor,
        profile_id: str,
        request: RelationshipUpdateRequest,
    ) -> RelationshipUpdateResponse: ...

    async def bind_accounts(
        self,
        *,
        actor: DatabaseActor,
        request: BindAccountsRequest,
    ) -> BindAccountsResponse: ...

    async def review_claim(
        self,
        *,
        actor: DatabaseActor,
        claim_id: str,
        approve: bool,
    ) -> ClaimReviewResponse: ...

    async def record_write_attempt(
        self,
        *,
        actor: DatabaseActor,
        operation: str,
        status: str,
        reason_code: str,
    ) -> None: ...

    async def list_control_operations(self, *, limit: int) -> list[ControlAuditEvent]: ...


class DatabaseControlService:
    def __init__(self, repository: DatabaseControlRepository) -> None:
        self._repository = repository

    async def resolve_read_actor(self, identity: ActorIdentity) -> DatabaseActor:
        actor = require_actor(await self._repository.resolve_actor(identity))
        require_read_admin(actor)
        return actor

    async def get_status(self, actor: DatabaseActor) -> DatabaseStatus:
        require_read_admin(actor)
        return await self._repository.get_status()

    async def get_admin(self, actor: DatabaseActor) -> AdminProfileResponse:
        require_read_admin(actor)
        result = await self._repository.get_admin_profile()
        if result is None:
            raise ResourceNotFoundError("admin profile does not exist")
        return result.model_copy(
            update={"accounts": [sanitized_account(account) for account in result.accounts]}
        )

    async def list_control_operations(
        self,
        actor: DatabaseActor,
        *,
        limit: int = 20,
    ) -> list[ControlAuditEvent]:
        require_read_admin(actor)
        return await self._repository.list_control_operations(limit=max(1, min(limit, 100)))

    async def list_profiles(
        self,
        actor: DatabaseActor,
        *,
        filters: ProfileFilters,
        limit: int,
        cursor: str | None,
    ) -> ProfilePage:
        require_read_admin(actor)
        return await self._repository.list_profiles(filters=filters, limit=limit, cursor=cursor)

    async def get_profile(self, actor: DatabaseActor, profile_id: str) -> ProfileDetail:
        require_read_admin(actor)
        result = await self._repository.get_profile(profile_id)
        if result is None:
            raise ResourceNotFoundError(f"profile not found: {profile_id}")
        return result.model_copy(
            update={
                "platform_accounts": [
                    sanitized_account(account) for account in result.platform_accounts
                ]
            }
        )

    async def bootstrap_admin(
        self,
        request: BootstrapAdminRequest,
        *,
        local_request: bool,
    ) -> BootstrapAdminResponse:
        return await self._repository.bootstrap_admin(request, local_request=local_request)

    async def set_profile_relationship(
        self,
        actor: DatabaseActor,
        profile_id: str,
        request: RelationshipUpdateRequest,
    ) -> RelationshipUpdateResponse:
        await self._require_write_ready(actor, operation="set_profile_relationship")
        return await self._repository.set_profile_relationship(
            actor=actor,
            profile_id=profile_id,
            request=request,
        )

    async def bind_accounts(
        self,
        actor: DatabaseActor,
        request: BindAccountsRequest,
    ) -> BindAccountsResponse:
        await self._require_write_ready(actor, operation="bind_accounts")
        return await self._repository.bind_accounts(actor=actor, request=request)

    async def review_claim(
        self,
        actor: DatabaseActor,
        claim_id: str,
        *,
        approve: bool,
    ) -> ClaimReviewResponse:
        await self._require_write_ready(
            actor, operation="approve_claim" if approve else "reject_claim"
        )
        return await self._repository.review_claim(
            actor=actor,
            claim_id=claim_id,
            approve=approve,
        )

    async def _require_write_ready(self, actor: DatabaseActor, *, operation: str) -> None:
        try:
            require_mutate_admin(actor)
        except ForbiddenError:
            await self._repository.record_write_attempt(
                actor=actor,
                operation=operation,
                status="rejected",
                reason_code="admin_required",
            )
            raise
        status = await self._repository.get_status()
        if not status.ready or not status.database_v2_enabled:
            await self._repository.record_write_attempt(
                actor=actor,
                operation=operation,
                status="rejected",
                reason_code="database_not_ready",
            )
            raise DatabaseNotReadyError("Database V2 is not ready for write operations")
