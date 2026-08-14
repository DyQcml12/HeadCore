from __future__ import annotations

from app.database_control.contracts import ActorIdentity, DatabaseActor
from app.database_control.errors import ForbiddenError, UnauthenticatedError


def require_actor(actor: DatabaseActor | None) -> DatabaseActor:
    if actor is None:
        raise UnauthenticatedError("database actor identity could not be resolved")
    return actor


def require_read_admin(actor: DatabaseActor) -> None:
    account_is_active = actor.source_account.status == "active"
    if (
        actor.relationship_type != "admin_partner"
        or not actor.permissions.read_admin
        or not account_is_active
    ):
        raise ForbiddenError("admin_partner permission is required")


def require_mutate_admin(actor: DatabaseActor) -> None:
    require_read_admin(actor)
    if not actor.permissions.mutate_admin:
        raise ForbiddenError("admin mutation permission is required")


def build_actor_identity(
    *,
    platform: str | None,
    platform_user_id: str | None,
    platform_group_id: str | None,
) -> ActorIdentity:
    normalized_platform = (platform or "").strip().lower()
    normalized_user_id = (platform_user_id or "").strip()
    if not normalized_platform or not normalized_user_id:
        raise UnauthenticatedError("actor platform and user id headers are required")
    if normalized_platform not in {"qq", "wechat", "core"}:
        raise UnauthenticatedError("actor platform is not supported")
    return ActorIdentity(
        platform=normalized_platform,  # type: ignore[arg-type]
        platform_user_id=normalized_user_id,
        platform_group_id=(platform_group_id or "").strip(),
    )
