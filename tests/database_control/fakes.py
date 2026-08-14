from __future__ import annotations

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
    SourceAccount,
)


def profile_summary(profile_id: str = "profile-admin") -> ProfileSummary:
    return ProfileSummary(
        id=profile_id,
        display_name="管理员" if profile_id == "profile-admin" else "测试用户",
        relationship_type="admin_partner" if profile_id == "profile-admin" else "normal_friend",
        verified=profile_id == "profile-admin",
        trust_level=100 if profile_id == "profile-admin" else 10,
        affection_level=100 if profile_id == "profile-admin" else 10,
        account_count=1,
        updated_at="2026-07-14T08:00:00Z",
    )


def account() -> PlatformAccountSummary:
    return PlatformAccountSummary(
        id="account-admin",
        platform="qq",
        platform_user_id="123456789",
        platform_group_id="987654",
        display_name="QQ昵称",
        is_primary=True,
        status="active",
    )


def actor(relationship_type: str = "admin_partner", status: str = "active") -> DatabaseActor:
    return DatabaseActor(
        profile_id="profile-admin" if relationship_type == "admin_partner" else "profile-user",
        relationship_type=relationship_type,
        permissions=DatabasePermissions(
            read_admin=relationship_type == "admin_partner",
            mutate_admin=relationship_type == "admin_partner",
        ),
        source_account=SourceAccount(
            id="account-actor",
            platform="qq",
            status=status,
        ),
    )


class FakeDatabaseControlRepository:
    def __init__(self, resolved_actor: DatabaseActor | None = None, *, ready: bool = True) -> None:
        self.resolved_actor = resolved_actor
        self.last_identity: ActorIdentity | None = None
        self.last_filters: ProfileFilters | None = None
        self.ready = ready
        self.write_attempts: list[tuple[str, str, str]] = []
        self.admin = AdminProfileResponse(
            profile=profile_summary(),
            accounts=[account()],
            private_profile_configured=True,
        )
        self.profiles = {"profile-user": ProfileDetail(**profile_summary("profile-user").model_dump(), platform_accounts=[account()])}

    async def resolve_actor(self, identity: ActorIdentity) -> DatabaseActor | None:
        self.last_identity = identity
        return self.resolved_actor

    async def get_status(self) -> DatabaseStatus:
        return DatabaseStatus(
            database="hutao_chat_core",
            schema_version="v2.001_hutao_chat_core_schema",
            ready=self.ready,
            database_v2_enabled=self.ready,
            required_tables={"profiles": True, "platform_accounts": True},
            admin_exists=True,
            legacy_database=LegacyDatabaseStatus(name="xiaohe_core", status="deprecated"),
        )

    async def get_admin_profile(self) -> AdminProfileResponse | None:
        return self.admin

    async def list_profiles(
        self,
        *,
        filters: ProfileFilters,
        limit: int,
        cursor: str | None,
    ) -> ProfilePage:
        self.last_filters = filters
        return ProfilePage(items=[profile_summary("profile-user")], next_cursor="cursor-2")

    async def get_profile(self, profile_id: str) -> ProfileDetail | None:
        return self.profiles.get(profile_id)

    async def bootstrap_admin(
        self, request: BootstrapAdminRequest, *, local_request: bool
    ) -> BootstrapAdminResponse:
        return BootstrapAdminResponse(
            profile_id="profile-admin",
            created=True,
            bound_accounts=[BoundAccount(platform="qq", platform_user_id="10*01")],
        )

    async def set_profile_relationship(
        self,
        *,
        actor: DatabaseActor,
        profile_id: str,
        request: RelationshipUpdateRequest,
    ) -> RelationshipUpdateResponse:
        return RelationshipUpdateResponse(
            profile_id=profile_id,
            old_relationship_type="normal_friend",
            new_relationship_type=request.relationship_type,
            verified=request.verified,
        )

    async def bind_accounts(
        self, *, actor: DatabaseActor, request: BindAccountsRequest
    ) -> BindAccountsResponse:
        return BindAccountsResponse(
            profile_id="profile-source",
            merged_profile_id="profile-target",
            status="bound",
        )

    async def review_claim(
        self, *, actor: DatabaseActor, claim_id: str, approve: bool
    ) -> ClaimReviewResponse:
        return ClaimReviewResponse(
            claim_id=claim_id,
            status="approved" if approve else "rejected",
        )

    async def record_write_attempt(
        self,
        *,
        actor: DatabaseActor,
        operation: str,
        status: str,
        reason_code: str,
    ) -> None:
        self.write_attempts.append((operation, status, reason_code))

    async def list_control_operations(self, *, limit: int) -> list[ControlAuditEvent]:
        return [
            ControlAuditEvent(
                audit_id="audit-1",
                operation="service_start",
                platform="qq",
                status="accepted",
                reason_code="completed",
                created_at="2026-07-15T00:00:00Z",
            )
        ][:limit]
