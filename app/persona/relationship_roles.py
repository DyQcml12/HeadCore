from __future__ import annotations

from typing import Literal

from app.storage.chat_repository import RelationshipRole


CanonicalRelationshipRole = Literal["admin_partner", "normal_friend", "blocked"]


NORMAL_FRIEND_STORAGE_ROLES = {"owner_friend", "owner_relative", "friend", "stranger"}


def canonical_relationship_role(role: str) -> CanonicalRelationshipRole:
    normalized = role.strip().lower()
    if normalized == "owner" or normalized == "admin_partner":
        return "admin_partner"
    if normalized == "blocked":
        return "blocked"
    return "normal_friend"


def relationship_bucket_label(role: str) -> str:
    bucket = canonical_relationship_role(role)
    return {
        "admin_partner": "管理员/爱人",
        "normal_friend": "普通朋友",
        "blocked": "黑名单",
    }[bucket]


def storage_role_for_related_alias(role: RelationshipRole) -> RelationshipRole:
    if role == "owner":
        return "owner"
    if role == "blocked":
        return "blocked"
    return "friend"
