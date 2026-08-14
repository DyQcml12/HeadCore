from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ActorPlatform = Literal["qq", "wechat", "core"]
RelationshipType = Literal["admin_partner", "normal_friend", "blocked"]
AccountStatus = Literal["active", "blocked", "disabled", "unbound"]


class ActorIdentity(BaseModel):
    platform: ActorPlatform
    platform_user_id: str = Field(min_length=1, max_length=255)
    platform_group_id: str = Field(default="", max_length=255)


class SourceAccount(BaseModel):
    id: str
    platform: ActorPlatform
    status: AccountStatus


class DatabasePermissions(BaseModel):
    read_admin: bool = False
    mutate_admin: bool = False


class DatabaseActor(BaseModel):
    profile_id: str
    relationship_type: RelationshipType
    permissions: DatabasePermissions
    source_account: SourceAccount


class LegacyDatabaseStatus(BaseModel):
    name: str
    status: str


class DatabaseStatus(BaseModel):
    database: str
    schema_version: str
    ready: bool
    database_v2_enabled: bool
    required_tables: dict[str, bool]
    admin_exists: bool
    legacy_database: LegacyDatabaseStatus | None = None


class ControlAuditEvent(BaseModel):
    audit_id: str
    operation: str
    platform: str
    status: Literal["accepted", "rejected", "failed"]
    reason_code: str
    created_at: str


class PlatformAccountSummary(BaseModel):
    id: str
    platform: Literal["qq", "wechat"]
    platform_user_id: str
    platform_group_id: str = ""
    display_name: str = ""
    account_label: str = "unknown"
    is_primary: bool = False
    status: AccountStatus = "active"
    last_seen_at: str | None = None


class SocialLabelSummary(BaseModel):
    label_type: str
    label_text: str
    verified: bool = False


class ProfileSummary(BaseModel):
    id: str
    display_name: str
    relationship_type: RelationshipType
    verified: bool
    trust_level: int = Field(ge=0, le=100)
    affection_level: int = Field(ge=0, le=100)
    status: str = "active"
    merged_into_profile_id: str | None = None
    account_count: int = Field(default=0, ge=0)
    last_seen_at: str | None = None
    labels: list[str] = Field(default_factory=list)
    updated_at: str


class ProfileDetail(ProfileSummary):
    platform_accounts: list[PlatformAccountSummary] = Field(default_factory=list)
    social_labels: list[SocialLabelSummary] = Field(default_factory=list)
    portrait_summary: dict[str, object] | None = None
    emotional_state: dict[str, object] | None = None
    recent_conversations: list[dict[str, object]] = Field(default_factory=list)
    latest_relationship_events: list[dict[str, object]] = Field(default_factory=list)
    memory_counts: dict[str, int] = Field(default_factory=dict)


class AdminProfileResponse(BaseModel):
    profile: ProfileSummary
    accounts: list[PlatformAccountSummary]
    private_profile_configured: bool


class ProfileFilters(BaseModel):
    relationship_type: RelationshipType | None = None
    verified: bool | None = None
    platform: Literal["qq", "wechat"] | None = None
    query: str = Field(default="", max_length=100)


class ProfilePage(BaseModel):
    items: list[ProfileSummary]
    next_cursor: str | None = None


class BootstrapAdminRequest(BaseModel):
    display_name: str = Field(default="admin", min_length=1, max_length=128)
    qq_ids: list[str] = Field(default_factory=list, max_length=20)
    wechat_ids: list[str] = Field(default_factory=list, max_length=20)


class BoundAccount(BaseModel):
    platform: Literal["qq", "wechat"]
    platform_user_id: str


class BootstrapAdminResponse(BaseModel):
    profile_id: str
    created: bool
    bound_accounts: list[BoundAccount]


class RelationshipUpdateRequest(BaseModel):
    relationship_type: RelationshipType
    verified: bool
    reason: str = Field(min_length=1, max_length=500)


class RelationshipUpdateResponse(BaseModel):
    profile_id: str
    old_relationship_type: RelationshipType
    new_relationship_type: RelationshipType
    verified: bool


class AccountIdentityInput(BaseModel):
    platform: Literal["qq", "wechat"]
    platform_user_id: str = Field(min_length=1, max_length=128)
    platform_group_id: str = Field(default="", max_length=128)


class BindAccountsRequest(BaseModel):
    source: AccountIdentityInput
    target: AccountIdentityInput
    target_profile_id: str | None = Field(default=None, max_length=36)
    confirm_merge: bool = False
    reason: str = Field(min_length=1, max_length=500)


class BindAccountsResponse(BaseModel):
    profile_id: str
    merged_profile_id: str | None
    status: Literal["bound", "already_bound"]


class ClaimReviewResponse(BaseModel):
    claim_id: str
    status: Literal["approved", "rejected"]
    profile_id: str | None = None
    relationship_type: RelationshipType | None = None


def redact_platform_user_id(value: str) -> str:
    value = value.strip()
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * min(8, len(value) - 4)}{value[-2:]}"


def sanitized_account(account: PlatformAccountSummary) -> PlatformAccountSummary:
    return account.model_copy(
        update={
            "platform_user_id": redact_platform_user_id(account.platform_user_id),
            "platform_group_id": "" if not account.platform_group_id else "<redacted>",
        }
    )
