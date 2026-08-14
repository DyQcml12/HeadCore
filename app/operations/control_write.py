from __future__ import annotations

from typing import Protocol

from app.database_control.actor import build_actor_identity, require_mutate_admin
from app.database_control.contracts import (
    ActorIdentity,
    DatabaseActor,
    DatabasePermissions,
    SourceAccount,
)
from app.database_control.errors import ForbiddenError


class ControlWriteRepository(Protocol):
    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None: ...

    async def record_control_operation(
        self,
        *,
        actor: DatabaseActor | None,
        platform: str,
        operation: str,
        status: str,
        reason_code: str,
    ) -> None: ...


class ControlWriteGuard:
    def __init__(
        self,
        repository: ControlWriteRepository,
        *,
        fallback_admin_accounts: dict[str, set[str]] | None = None,
    ) -> None:
        self._repository = repository
        self._fallback_admin_accounts = {
            platform.strip().lower(): {value.strip() for value in values if value.strip()}
            for platform, values in (fallback_admin_accounts or {}).items()
        }

    async def _resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None:
        try:
            actor = await self._repository.resolve_actor(identity)
        except Exception:
            actor = None
        if actor is not None:
            return actor
        allowed_ids = self._fallback_admin_accounts.get(identity.platform, set())
        if identity.platform_user_id not in allowed_ids:
            return None
        return DatabaseActor(
            profile_id="bootstrap-admin",
            relationship_type="admin_partner",
            permissions=DatabasePermissions(read_admin=True, mutate_admin=True),
            source_account=SourceAccount(
                id=f"bootstrap-{identity.platform}",
                platform=identity.platform,
                status="active",
            ),
        )

    async def authorize(
        self,
        *,
        platform: str | None,
        user_id: str | None,
        group_id: str | None,
        operation: str,
    ) -> DatabaseActor:
        actor: DatabaseActor | None = None
        audit_platform = (platform or "core").strip().lower() or "core"
        try:
            identity = build_actor_identity(
                platform=platform,
                platform_user_id=user_id,
                platform_group_id=group_id,
            )
            actor = await self._resolve_actor(identity)
            if actor is None:
                raise ForbiddenError("administrator actor is required")
            require_mutate_admin(actor)
        except Exception as exc:
            await self._audit(
                actor=actor,
                platform=audit_platform,
                operation=operation,
                status="rejected",
                reason_code="admin_required",
            )
            if isinstance(exc, ForbiddenError):
                raise
            raise ForbiddenError("administrator actor is required") from exc
        return actor

    async def verify(
        self,
        *,
        platform: str | None,
        user_id: str | None,
        group_id: str | None,
    ) -> DatabaseActor | None:
        try:
            identity = build_actor_identity(
                platform=platform,
                platform_user_id=user_id,
                platform_group_id=group_id,
            )
            actor = await self._resolve_actor(identity)
            if actor is None:
                return None
            require_mutate_admin(actor)
            return actor
        except Exception:
            return None

    async def record_result(
        self,
        *,
        actor: DatabaseActor,
        operation: str,
        success: bool,
        reason_code: str,
    ) -> None:
        await self._audit(
            actor=actor,
            platform=actor.source_account.platform,
            operation=operation,
            status="accepted" if success else "failed",
            reason_code=reason_code,
        )

    async def _audit(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        try:
            await self._repository.record_control_operation(**kwargs)
        except Exception:
            pass
