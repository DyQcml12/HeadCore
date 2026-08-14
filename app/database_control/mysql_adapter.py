from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from app.core.config import Settings
from app.database_control.contracts import (
    ActorIdentity,
    AdminProfileResponse,
    BindAccountsRequest,
    BindAccountsResponse,
    BootstrapAdminRequest,
    BootstrapAdminResponse,
    BoundAccount,
    ClaimReviewResponse,
    ControlAuditEvent,
    DatabaseActor,
    DatabasePermissions,
    DatabaseStatus,
    LegacyDatabaseStatus,
    PlatformAccountSummary,
    ProfileDetail,
    ProfileFilters,
    ProfilePage,
    ProfileSummary,
    RelationshipUpdateRequest,
    RelationshipUpdateResponse,
    SocialLabelSummary,
    SourceAccount,
)
from app.database_control.errors import (
    DatabaseNotReadyError,
    ForbiddenError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository
from app.storage.v2_relationship_service import parse_bootstrap_ids
from app.storage.v2_repository import DATABASE_V2_SCHEMA_VERSION


CONTROL_REQUIRED_TABLES = (
    "profiles",
    "platform_accounts",
    "admin_profile",
    "conversations",
    "messages",
)


class MySQLDatabaseControlAdapter:
    def __init__(
        self,
        settings: Settings,
        repository: MySQLDatabaseV2Repository | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository

    def _get_repository(self) -> MySQLDatabaseV2Repository:
        if self._repository is None:
            self._repository = MySQLDatabaseV2Repository(self._settings)
        return self._repository

    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None:
        if identity.platform not in {"qq", "wechat"}:
            return None
        context = await self._get_repository().find_relationship_context(
            platform=identity.platform,
            platform_user_id=identity.platform_user_id,
            platform_group_id=identity.platform_group_id,
        )
        if context is None:
            return None
        is_admin = (
            context.effective_relationship_type == "admin_partner"
            and context.platform_account.status == "active"
            and context.permissions.can_view_chat_history
        )
        return DatabaseActor(
            profile_id=context.profile.id,
            relationship_type=context.effective_relationship_type,
            permissions=DatabasePermissions(read_admin=is_admin, mutate_admin=is_admin),
            source_account=SourceAccount(
                id=context.platform_account.id,
                platform=context.platform_account.platform,
                status=context.platform_account.status,
            ),
        )

    async def get_status(self) -> DatabaseStatus:
        snapshot = await self._get_repository().get_control_status_snapshot(
            required_tables=CONTROL_REQUIRED_TABLES
        )
        tables = set(snapshot["tables"])
        required = {table: table in tables for table in CONTROL_REQUIRED_TABLES}
        schema_version = str(snapshot["schema_version"])
        admin_exists = bool(snapshot["admin_exists"])
        return DatabaseStatus(
            database=self._settings.mysql_database,
            schema_version=schema_version,
            ready=(
                schema_version == DATABASE_V2_SCHEMA_VERSION
                and all(required.values())
                and admin_exists
            ),
            database_v2_enabled=self._settings.database_v2_enabled,
            required_tables=required,
            admin_exists=admin_exists,
            legacy_database=LegacyDatabaseStatus(name="legacy_chat_core", status="deprecated"),
        )

    async def get_admin_profile(self) -> AdminProfileResponse | None:
        snapshot = await self._get_repository().get_admin_profile_snapshot()
        if snapshot is None:
            return None
        accounts = [_account_from_row(row) for row in snapshot["accounts"]]
        profile = _profile_from_row(snapshot["profile"], account_count=len(accounts))
        return AdminProfileResponse(
            profile=profile,
            accounts=accounts,
            private_profile_configured=bool(
                snapshot["profile"].get("private_profile_configured")
            ),
        )

    async def list_profiles(
        self,
        *,
        filters: ProfileFilters,
        limit: int,
        cursor: str | None,
    ) -> ProfilePage:
        cursor_updated_at, cursor_profile_id = _decode_cursor(cursor)
        rows = await self._get_repository().list_profile_snapshots(
            relationship_type=filters.relationship_type,
            verified=filters.verified,
            platform=filters.platform,
            query=filters.query.strip(),
            limit=limit + 1,
            cursor_updated_at=cursor_updated_at,
            cursor_profile_id=cursor_profile_id,
        )
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        next_cursor = None
        if has_more and visible_rows:
            last = visible_rows[-1]
            next_cursor = _encode_cursor(str(last["updated_at"]), str(last["id"]))
        return ProfilePage(
            items=[_profile_from_row(row) for row in visible_rows],
            next_cursor=next_cursor,
        )

    async def get_profile(self, profile_id: str) -> ProfileDetail | None:
        snapshot = await self._get_repository().get_profile_detail_snapshot(profile_id=profile_id)
        if snapshot is None:
            return None
        profile = _profile_from_row(snapshot["profile"])
        return ProfileDetail(
            **profile.model_dump(),
            platform_accounts=[_account_from_row(row) for row in snapshot["accounts"]],
            social_labels=[
                SocialLabelSummary(
                    label_type=str(row["label_type"]),
                    label_text=str(row.get("label_text") or ""),
                    verified=bool(row.get("verified")),
                )
                for row in snapshot["labels"]
            ],
            portrait_summary=_json_safe_mapping(snapshot["portrait"]),
            emotional_state=_json_safe_mapping(snapshot["emotion"]),
            recent_conversations=[_json_safe_mapping(row) or {} for row in snapshot["conversations"]],
            latest_relationship_events=[_json_safe_mapping(row) or {} for row in snapshot["events"]],
            memory_counts={
                str(row["scope"]): int(row["memory_count"])
                for row in snapshot["memory_counts"]
            },
        )

    async def bootstrap_admin(
        self,
        request: BootstrapAdminRequest,
        *,
        local_request: bool,
    ) -> BootstrapAdminResponse:
        if not local_request:
            raise ForbiddenError("admin bootstrap is restricted to local setup")
        configured_qq = set(parse_bootstrap_ids(self._settings.owner_bootstrap_qq_ids))
        configured_wechat = set(parse_bootstrap_ids(self._settings.owner_bootstrap_wechat_ids))
        qq_ids = _clean_ids(request.qq_ids)
        wechat_ids = _clean_ids(request.wechat_ids)
        if not qq_ids and not wechat_ids:
            raise ResourceConflictError("at least one bootstrap account is required")
        if not configured_qq and not configured_wechat:
            raise ForbiddenError("owner bootstrap ids are not configured")
        if not set(qq_ids).issubset(configured_qq) or not set(wechat_ids).issubset(configured_wechat):
            raise ForbiddenError("bootstrap accounts do not match configured owner ids")
        status = await self.get_status()
        schema_ready = (
            status.schema_version == DATABASE_V2_SCHEMA_VERSION
            and all(status.required_tables.values())
            and status.database_v2_enabled
        )
        if not schema_ready:
            raise DatabaseNotReadyError("Database V2 schema is not ready for admin bootstrap")
        if status.admin_exists:
            raise ResourceConflictError("admin profile already exists")
        profile_id = await self._get_repository().bootstrap_admin_if_missing(
            qq_ids=qq_ids,
            wechat_ids=wechat_ids,
            display_name=request.display_name,
        )
        if profile_id is None:
            raise ResourceConflictError("admin profile already exists")
        accounts = [
            BoundAccount(platform="qq", platform_user_id=_redact_id(value)) for value in qq_ids
        ] + [
            BoundAccount(platform="wechat", platform_user_id=_redact_id(value))
            for value in wechat_ids
        ]
        return BootstrapAdminResponse(
            profile_id=profile_id,
            created=True,
            bound_accounts=accounts,
        )

    async def set_profile_relationship(
        self,
        *,
        actor: DatabaseActor,
        profile_id: str,
        request: RelationshipUpdateRequest,
    ) -> RelationshipUpdateResponse:
        result = await self._get_repository().update_profile_relationship(
            profile_id=profile_id,
            relationship_type=request.relationship_type,
            verified=request.verified,
            changed_by_profile_id=actor.profile_id,
            reason=request.reason,
        )
        status = str(result.get("status"))
        if status == "not_found":
            await self._audit(actor, "set_profile_relationship", "rejected", "not_found")
            raise ResourceNotFoundError(f"profile not found: {profile_id}")
        if status == "admin_transfer_required":
            await self._audit(actor, "set_profile_relationship", "rejected", "conflict")
            raise ResourceConflictError("admin_partner requires a dedicated admin transfer")
        await self._audit(actor, "set_profile_relationship", "accepted", status)
        return RelationshipUpdateResponse(
            profile_id=profile_id,
            old_relationship_type=str(result["old_relationship_type"]),  # type: ignore[arg-type]
            new_relationship_type=str(result["new_relationship_type"]),  # type: ignore[arg-type]
            verified=bool(result["verified"]),
        )

    async def bind_accounts(
        self,
        *,
        actor: DatabaseActor,
        request: BindAccountsRequest,
    ) -> BindAccountsResponse:
        source = await self._get_repository().find_relationship_context(
            platform=request.source.platform,
            platform_user_id=request.source.platform_user_id,
            platform_group_id=request.source.platform_group_id,
        )
        target = await self._get_repository().find_relationship_context(
            platform=request.target.platform,
            platform_user_id=request.target.platform_user_id,
            platform_group_id=request.target.platform_group_id,
        )
        if source is None or target is None:
            await self._audit(actor, "bind_accounts", "rejected", "not_found")
            raise ResourceNotFoundError("source or target platform account was not found")
        if source.profile.id == target.profile.id:
            await self._audit(actor, "bind_accounts", "accepted", "already_bound")
            return BindAccountsResponse(
                profile_id=source.profile.id,
                merged_profile_id=None,
                status="already_bound",
            )
        if not request.confirm_merge:
            await self._audit(actor, "bind_accounts", "rejected", "merge_confirmation_required")
            raise ResourceConflictError(
                f"merge confirmation required for profiles {source.profile.id} and {target.profile.id}"
            )
        survivor = source
        merged = target
        source_identity = request.source
        target_identity = request.target
        if request.target_profile_id is not None:
            if request.target_profile_id == target.profile.id:
                survivor, merged = target, source
                source_identity, target_identity = request.target, request.source
            elif request.target_profile_id != source.profile.id:
                await self._audit(actor, "bind_accounts", "rejected", "target_profile_mismatch")
                raise ResourceConflictError("target_profile_id does not match either account profile")
        profile_id = await self._get_repository().bind_accounts(
            source_platform=source_identity.platform,
            source_platform_user_id=source_identity.platform_user_id,
            target_platform=target_identity.platform,
            target_platform_user_id=target_identity.platform_user_id,
            changed_by_profile_id=actor.profile_id,
            reason=request.reason,
        )
        await self._audit(actor, "bind_accounts", "accepted", "bound")
        return BindAccountsResponse(
            profile_id=profile_id,
            merged_profile_id=merged.profile.id,
            status="bound",
        )

    async def review_claim(
        self,
        *,
        actor: DatabaseActor,
        claim_id: str,
        approve: bool,
    ) -> ClaimReviewResponse:
        if approve:
            result = await self._get_repository().approve_relationship_claim(
                claim_id=claim_id,
                reviewed_by_profile_id=actor.profile_id,
            )
        else:
            result = await self._get_repository().reject_relationship_claim(
                claim_id=claim_id,
                reviewed_by_profile_id=actor.profile_id,
            )
        status = str(result.get("status"))
        if status == "not_found":
            await self._audit(
                actor, "approve_claim" if approve else "reject_claim", "rejected", "not_found"
            )
            raise ResourceNotFoundError(f"claim not found: {claim_id}")
        if status == "already_reviewed":
            await self._audit(
                actor,
                "approve_claim" if approve else "reject_claim",
                "rejected",
                "already_reviewed",
            )
            raise ResourceConflictError(f"claim already reviewed: {claim_id}")
        await self._audit(
            actor, "approve_claim" if approve else "reject_claim", "accepted", status
        )
        return ClaimReviewResponse(
            claim_id=claim_id,
            status=status,  # type: ignore[arg-type]
            profile_id=str(result["profile_id"]) if result.get("profile_id") else None,
            relationship_type=result.get("relationship_type"),  # type: ignore[arg-type]
        )

    async def record_write_attempt(
        self,
        *,
        actor: DatabaseActor,
        operation: str,
        status: str,
        reason_code: str,
    ) -> None:
        await self._audit(actor, operation, status, reason_code)

    async def record_control_operation(
        self,
        *,
        actor: DatabaseActor | None,
        actor_profile_id: str | None = None,
        platform: str,
        operation: str,
        status: str,
        reason_code: str,
    ) -> None:
        await self._get_repository().record_database_control_event(
            actor_profile_id=(actor.profile_id if actor is not None else actor_profile_id),
            platform=platform,
            command_name=operation,
            status=status,
            reason_code=reason_code,
        )

    async def list_control_operations(self, *, limit: int) -> list[ControlAuditEvent]:
        rows = await self._get_repository().list_database_control_events(limit=limit)
        return [
            ControlAuditEvent(
                audit_id=str(row["id"]),
                operation=str(row["command_name"]),
                platform=str(row["platform"]),
                status=str(row["status"]),  # type: ignore[arg-type]
                reason_code=str(row.get("reason_code") or ""),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def _audit(
        self,
        actor: DatabaseActor,
        operation: str,
        status: str,
        reason_code: str,
    ) -> None:
        await self._get_repository().record_database_control_event(
            actor_profile_id=actor.profile_id,
            platform=actor.source_account.platform,
            command_name=operation,
            status=status,
            reason_code=reason_code,
        )


def _profile_from_row(row: dict[str, Any], *, account_count: int | None = None) -> ProfileSummary:
    labels_text = str(row.get("labels_text") or "")
    return ProfileSummary(
        id=str(row["id"]),
        display_name=str(row.get("display_name") or ""),
        relationship_type=str(row["relationship_type"]),  # type: ignore[arg-type]
        verified=bool(row.get("verified")),
        trust_level=int(row.get("trust_level") or 0),
        affection_level=int(row.get("affection_level") or 0),
        status=str(row.get("status") or "active"),
        merged_into_profile_id=(
            str(row["merged_into_profile_id"])
            if row.get("merged_into_profile_id") is not None
            else None
        ),
        account_count=account_count if account_count is not None else int(row.get("account_count") or 0),
        last_seen_at=str(row["last_seen_at"]) if row.get("last_seen_at") is not None else None,
        labels=[item for item in labels_text.split("\n") if item],
        updated_at=str(row["updated_at"]),
    )


def _account_from_row(row: dict[str, Any]) -> PlatformAccountSummary:
    return PlatformAccountSummary(
        id=str(row["id"]),
        platform=str(row["platform"]),  # type: ignore[arg-type]
        platform_user_id=str(row["platform_user_id"]),
        platform_group_id=str(row.get("platform_group_id") or ""),
        display_name=str(row.get("display_name") or ""),
        account_label=str(row.get("account_label") or "unknown"),
        is_primary=bool(row.get("is_primary")),
        status=str(row.get("status") or "active"),  # type: ignore[arg-type]
        last_seen_at=str(row["last_seen_at"]) if row.get("last_seen_at") is not None else None,
    )


def _encode_cursor(updated_at: str, profile_id: str) -> str:
    payload = json.dumps({"updated_at": updated_at, "profile_id": profile_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[str | None, str | None]:
    if not cursor:
        return None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        updated_at = value["updated_at"]
        profile_id = value["profile_id"]
        if not isinstance(updated_at, str) or not isinstance(profile_id, str):
            raise ValueError
        return updated_at, profile_id
    except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error) as exc:
        raise ResourceConflictError("profile cursor is invalid") from exc


def _json_safe_mapping(row: dict[str, Any] | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {key: value if value is None or isinstance(value, (str, int, float, bool)) else str(value) for key, value in row.items()}


def _clean_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _redact_id(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * min(8, len(value) - 4)}{value[-2:]}"


def build_mysql_database_control_adapter(settings: Settings) -> MySQLDatabaseControlAdapter:
    return MySQLDatabaseControlAdapter(settings)
