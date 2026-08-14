from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

from app.core.config import Settings
from app.storage.v2_models import PlatformName, V2RelationshipContext
from app.storage.v2_repository import DatabaseV2Repository


ConversationType = Literal["private", "group"]


@dataclass(frozen=True)
class PlatformIdentity:
    platform: PlatformName
    platform_user_id: str
    platform_group_id: str | None = None
    display_name: str = ""
    conversation_type: ConversationType = "private"


@dataclass(frozen=True)
class RelationshipResolution:
    context: V2RelationshipContext
    should_enter_chat_service: bool
    should_reply: bool
    fixed_reply: str | None
    reason_code: str

    def to_model_context(self) -> dict[str, object]:
        profile = self.context.profile
        return {
            "relationship_type": profile.relationship_type,
            "effective_relationship_type": self.context.effective_relationship_type,
            "verified": profile.verified,
            "social_labels": list(self.context.social_labels),
            "permissions": asdict(self.context.permissions),
        }


class DatabaseV2RelationshipService:
    def __init__(self, repository: DatabaseV2Repository) -> None:
        self.repository = repository

    async def bootstrap_admin_from_settings(
        self,
        settings: Settings,
        *,
        display_name: str | None = None,
    ) -> str | None:
        return await self.repository.bootstrap_admin_if_missing(
            qq_ids=parse_bootstrap_ids(settings.owner_bootstrap_qq_ids),
            wechat_ids=parse_bootstrap_ids(settings.owner_bootstrap_wechat_ids),
            display_name=display_name or settings.hutao_owner_name or "admin",
        )

    async def resolve(self, identity: PlatformIdentity) -> RelationshipResolution:
        context = await self.repository.resolve_relationship_context(
            platform=identity.platform,
            platform_user_id=identity.platform_user_id,
            platform_group_id=identity.platform_group_id,
            display_name=identity.display_name,
        )
        if context.effective_relationship_type == "blocked":
            return RelationshipResolution(
                context=context,
                should_enter_chat_service=False,
                should_reply=identity.conversation_type == "private",
                fixed_reply="现在不方便继续聊。",
                reason_code="blocked_profile_or_account",
            )
        return RelationshipResolution(
            context=context,
            should_enter_chat_service=True,
            should_reply=True,
            fixed_reply=None,
            reason_code="allowed",
        )


def parse_bootstrap_ids(raw_value: str) -> list[str]:
    values: list[str] = []
    for item in re.split(r"[,;，；\s]+", raw_value.strip()):
        item = item.strip()
        if item and item not in values:
            values.append(item)
    return values
