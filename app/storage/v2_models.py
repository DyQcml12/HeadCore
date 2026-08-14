from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal


RelationshipType = Literal["admin_partner", "normal_friend", "blocked"]
PlatformName = Literal["qq", "wechat"]
AccountStatus = Literal["active", "blocked", "disabled", "unbound"]
PersonaBindingScope = Literal["fallback", "global", "relationship_type", "profile", "platform", "conversation"]


@dataclass(frozen=True)
class V2Permissions:
    can_view_owner_private: bool
    can_view_chat_history: bool
    can_set_relationship: bool
    can_bind_accounts: bool
    can_use_voice: bool
    can_write_long_term_memory: bool


@dataclass(frozen=True)
class V2Profile:
    id: str
    display_name: str
    relationship_type: RelationshipType
    verified: bool
    trust_level: int
    affection_level: int
    notes: str
    status: str
    merged_into_profile_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class V2PlatformAccount:
    id: str
    profile_id: str
    platform: PlatformName
    platform_user_id: str
    platform_group_id: str
    display_name: str
    account_label: str
    is_primary: bool
    status: AccountStatus
    confidence: int
    verified_by_profile_id: str | None
    last_seen_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class V2RelationshipContext:
    profile: V2Profile
    platform_account: V2PlatformAccount
    effective_relationship_type: RelationshipType
    permissions: V2Permissions
    social_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class V2Persona:
    id: str
    code: str
    display_name: str
    description: str
    status: str
    default_for_admin: bool
    default_for_normal_friend: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class V2PersonaVersion:
    id: str
    persona_id: str
    version_label: str
    prompt_template: str
    style_rules_json: dict[str, Any]
    safety_rules_json: dict[str, Any]
    memory_policy_json: dict[str, Any]
    active: bool
    created_by_profile_id: str | None
    created_at: str


@dataclass(frozen=True)
class V2PersonaContext:
    persona: V2Persona
    version: V2PersonaVersion | None
    source_scope: PersonaBindingScope
    state_json: dict[str, Any]


@dataclass(frozen=True)
class V2RecentChat:
    conversation_id: str
    platform: str
    conversation_type: str
    platform_thread_id: str
    title: str
    owner_profile_id: str | None
    owner_display_name: str
    owner_relationship_type: RelationshipType
    last_message_at: str | None
    message_count: int


@dataclass(frozen=True)
class V2ChatMessage:
    id: str
    conversation_id: str
    profile_id: str | None
    platform_account_id: str | None
    platform: str
    platform_message_id: str | None
    direction: str
    role: str
    content_type: str
    content: str
    safety_status: str
    memory_eligible: bool
    visible_to_admin: bool
    created_at: str
    conversation_title: str


@dataclass(frozen=True)
class V2PendingRelationshipClaim:
    id: str
    platform: PlatformName
    platform_user_id: str
    claimed_name: str
    claimed_relation_text: str
    status: str
    reviewed_by_profile_id: str | None
    created_at: str
    reviewed_at: str | None


ADMIN_PARTNER_PERMISSIONS = V2Permissions(
    can_view_owner_private=True,
    can_view_chat_history=True,
    can_set_relationship=True,
    can_bind_accounts=True,
    can_use_voice=True,
    can_write_long_term_memory=True,
)

NORMAL_FRIEND_PERMISSIONS = V2Permissions(
    can_view_owner_private=False,
    can_view_chat_history=False,
    can_set_relationship=False,
    can_bind_accounts=False,
    can_use_voice=False,
    can_write_long_term_memory=False,
)

BLOCKED_PERMISSIONS = V2Permissions(
    can_view_owner_private=False,
    can_view_chat_history=False,
    can_set_relationship=False,
    can_bind_accounts=False,
    can_use_voice=False,
    can_write_long_term_memory=False,
)


def permissions_for_relationship(relationship_type: RelationshipType) -> V2Permissions:
    if relationship_type == "admin_partner":
        return ADMIN_PARTNER_PERMISSIONS
    if relationship_type == "blocked":
        return BLOCKED_PERMISSIONS
    return NORMAL_FRIEND_PERMISSIONS


def normalize_platform_group_id(platform_group_id: str | None) -> str:
    return (platform_group_id or "").strip()


def normalize_relationship_type(value: str) -> RelationshipType:
    if value == "admin_partner":
        return "admin_partner"
    if value == "blocked":
        return "blocked"
    return "normal_friend"


def profile_from_row(row: dict[str, Any]) -> V2Profile:
    return V2Profile(
        id=str(row["id"]),
        display_name=str(row["display_name"]),
        relationship_type=normalize_relationship_type(str(row["relationship_type"])),
        verified=bool(row["verified"]),
        trust_level=int(row["trust_level"]),
        affection_level=int(row["affection_level"]),
        notes=str(row.get("notes") or ""),
        status=str(row.get("status") or "active"),
        merged_into_profile_id=(
            str(row["merged_into_profile_id"])
            if row.get("merged_into_profile_id") is not None
            else None
        ),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def account_from_row(row: dict[str, Any]) -> V2PlatformAccount:
    status = str(row.get("account_status") or row.get("status") or "active")
    if status not in {"active", "blocked", "disabled", "unbound"}:
        status = "active"
    platform = str(row["platform"])
    if platform not in {"qq", "wechat"}:
        raise ValueError(f"Unsupported platform from database: {platform}")
    return V2PlatformAccount(
        id=str(row["account_id"] if "account_id" in row else row["id"]),
        profile_id=str(row["profile_id"]),
        platform=platform,  # type: ignore[arg-type]
        platform_user_id=str(row["platform_user_id"]),
        platform_group_id=str(row.get("platform_group_id") or ""),
        display_name=str(row.get("account_display_name") or row.get("display_name") or ""),
        account_label=str(row.get("account_label") or "unknown"),
        is_primary=bool(row.get("is_primary")),
        status=status,  # type: ignore[arg-type]
        confidence=int(row.get("confidence") or 0),
        verified_by_profile_id=(
            str(row["verified_by_profile_id"])
            if row.get("verified_by_profile_id") is not None
            else None
        ),
        last_seen_at=str(row["last_seen_at"]) if row.get("last_seen_at") is not None else None,
        created_at=str(row["account_created_at"] if "account_created_at" in row else row["created_at"]),
        updated_at=str(row["account_updated_at"] if "account_updated_at" in row else row["updated_at"]),
    )


def recent_chat_from_row(row: dict[str, Any]) -> V2RecentChat:
    return V2RecentChat(
        conversation_id=str(row["conversation_id"] if "conversation_id" in row else row["id"]),
        platform=str(row["platform"]),
        conversation_type=str(row["conversation_type"]),
        platform_thread_id=str(row["platform_thread_id"]),
        title=str(row.get("title") or ""),
        owner_profile_id=str(row["owner_profile_id"]) if row.get("owner_profile_id") is not None else None,
        owner_display_name=str(row.get("owner_display_name") or ""),
        owner_relationship_type=normalize_relationship_type(str(row.get("owner_relationship_type") or "")),
        last_message_at=str(row["last_message_at"]) if row.get("last_message_at") is not None else None,
        message_count=int(row.get("message_count") or 0),
    )


def chat_message_from_row(row: dict[str, Any]) -> V2ChatMessage:
    return V2ChatMessage(
        id=str(row["id"]),
        conversation_id=str(row["conversation_id"]),
        profile_id=str(row["profile_id"]) if row.get("profile_id") is not None else None,
        platform_account_id=(
            str(row["platform_account_id"]) if row.get("platform_account_id") is not None else None
        ),
        platform=str(row["platform"]),
        platform_message_id=(
            str(row["platform_message_id"]) if row.get("platform_message_id") is not None else None
        ),
        direction=str(row["direction"]),
        role=str(row["role"]),
        content_type=str(row["content_type"]),
        content=str(row.get("content") or ""),
        safety_status=str(row.get("safety_status") or "not_checked"),
        memory_eligible=bool(row.get("memory_eligible")),
        visible_to_admin=bool(row.get("visible_to_admin")),
        created_at=str(row["created_at"]),
        conversation_title=str(row.get("conversation_title") or ""),
    )


def pending_claim_from_row(row: dict[str, Any]) -> V2PendingRelationshipClaim:
    platform = str(row["platform"])
    if platform not in {"qq", "wechat"}:
        raise ValueError(f"Unsupported platform from claim: {platform}")
    return V2PendingRelationshipClaim(
        id=str(row["id"]),
        platform=platform,  # type: ignore[arg-type]
        platform_user_id=str(row["platform_user_id"]),
        claimed_name=str(row.get("claimed_name") or ""),
        claimed_relation_text=str(row.get("claimed_relation_text") or ""),
        status=str(row.get("status") or "pending"),
        reviewed_by_profile_id=(
            str(row["reviewed_by_profile_id"])
            if row.get("reviewed_by_profile_id") is not None
            else None
        ),
        created_at=str(row["created_at"]),
        reviewed_at=str(row["reviewed_at"]) if row.get("reviewed_at") is not None else None,
    )


def _json_dict_from_row(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def persona_from_row(row: dict[str, Any]) -> V2Persona:
    return V2Persona(
        id=str(row["persona_id"] if "persona_id" in row else row["id"]),
        code=str(row.get("persona_code") or row.get("code") or ""),
        display_name=str(row.get("persona_display_name") or row.get("display_name") or ""),
        description=str(row.get("persona_description") or row.get("description") or ""),
        status=str(row.get("persona_status") or row.get("status") or "active"),
        default_for_admin=bool(row.get("default_for_admin")),
        default_for_normal_friend=bool(row.get("default_for_normal_friend")),
        created_at=str(row.get("persona_created_at") or row.get("created_at") or ""),
        updated_at=str(row.get("persona_updated_at") or row.get("updated_at") or ""),
    )


def persona_version_from_row(row: dict[str, Any]) -> V2PersonaVersion | None:
    version_id = row.get("persona_version_id") or row.get("version_id")
    if version_id is None:
        return None
    return V2PersonaVersion(
        id=str(version_id),
        persona_id=str(row["persona_id"]),
        version_label=str(row.get("version_label") or ""),
        prompt_template=str(row.get("prompt_template") or ""),
        style_rules_json=_json_dict_from_row(row, "style_rules_json"),
        safety_rules_json=_json_dict_from_row(row, "safety_rules_json"),
        memory_policy_json=_json_dict_from_row(row, "memory_policy_json"),
        active=bool(row.get("version_active", row.get("active", False))),
        created_by_profile_id=(
            str(row["created_by_profile_id"]) if row.get("created_by_profile_id") is not None else None
        ),
        created_at=str(row.get("version_created_at") or row.get("created_at") or ""),
    )


def persona_context_from_row(
    row: dict[str, Any],
    *,
    source_scope: PersonaBindingScope,
) -> V2PersonaContext:
    return V2PersonaContext(
        persona=persona_from_row(row),
        version=persona_version_from_row(row),
        source_scope=source_scope,
        state_json=_json_dict_from_row(row, "state_json"),
    )


def fallback_persona_context(relationship_type: RelationshipType) -> V2PersonaContext:
    return V2PersonaContext(
        persona=V2Persona(
            id="",
            code="hutao_v1",
            display_name="胡桃",
            description="fallback persona registry profile before database projection is initialized",
            status="active",
            default_for_admin=True,
            default_for_normal_friend=True,
            created_at="",
            updated_at="",
        ),
        version=None,
        source_scope="fallback",
        state_json={},
    )


def build_relationship_context(
    *,
    profile: V2Profile,
    platform_account: V2PlatformAccount,
    social_labels: tuple[str, ...] = (),
) -> V2RelationshipContext:
    effective = (
        "blocked"
        if profile.relationship_type == "blocked" or platform_account.status == "blocked"
        else profile.relationship_type
    )
    return V2RelationshipContext(
        profile=profile,
        platform_account=platform_account,
        effective_relationship_type=effective,
        permissions=permissions_for_relationship(effective),
        social_labels=social_labels,
    )
