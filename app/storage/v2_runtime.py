from __future__ import annotations

from app.core.config import Settings
from app.schemas import ChatResponse
from app.storage.chat_repository import ChatRepository
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository
from app.storage.v2_platform_command_service import DatabaseV2PlatformCommandService
from app.storage.v2_relationship_service import DatabaseV2RelationshipService, PlatformIdentity


def should_use_database_v2(
    settings: Settings,
    *,
    platform: str | None,
    platform_user_id: str | None,
    trusted_core_profile: bool = False,
) -> bool:
    if not settings.database_v2_enabled:
        return False
    if trusted_core_profile:
        return True
    return platform in {"qq", "wechat"} and bool((platform_user_id or "").strip())


def build_database_v2_platform_command_service(
    settings: Settings,
    *,
    command_prefixes: tuple[str, ...] = ("胡桃",),
) -> DatabaseV2PlatformCommandService:
    repository = MySQLDatabaseV2Repository(settings)
    relationship_service = DatabaseV2RelationshipService(repository)
    return DatabaseV2PlatformCommandService(
        relationship_service=relationship_service,
        repository=repository,
        command_prefixes=command_prefixes,
    )


def build_database_v2_chat_repository(settings: Settings) -> ChatRepository:
    return MySQLDatabaseV2Repository(settings)


def database_v2_chat_user_id(
    *,
    platform: str | None,
    platform_user_id: str | None,
    fallback_user_id: str,
) -> str:
    if platform in {"qq", "wechat"} and platform_user_id:
        return f"{platform}-{platform_user_id.strip()}"
    return fallback_user_id


async def try_handle_database_v2_platform_message(
    *,
    settings: Settings,
    platform: str | None,
    platform_user_id: str | None,
    platform_group_id: str | None,
    display_name: str = "",
    conversation_type: str = "private",
    message_text: str,
    message_id: str | None = None,
    command_prefixes: tuple[str, ...] = ("胡桃",),
    command_service: DatabaseV2PlatformCommandService | None = None,
) -> ChatResponse | None:
    if not should_use_database_v2(
        settings,
        platform=platform,
        platform_user_id=platform_user_id,
    ):
        return None
    if platform not in {"qq", "wechat"}:
        return None
    if conversation_type not in {"private", "group"}:
        conversation_type = "private"

    service = command_service or build_database_v2_platform_command_service(
        settings,
        command_prefixes=command_prefixes,
    )
    await service.relationship_service.bootstrap_admin_from_settings(settings)
    result = await service.handle_message(
        identity=PlatformIdentity(
            platform=platform,  # type: ignore[arg-type]
            platform_user_id=(platform_user_id or "").strip(),
            platform_group_id=platform_group_id,
            display_name=display_name,
            conversation_type=conversation_type,  # type: ignore[arg-type]
        ),
        message_text=message_text,
        message_id=message_id,
    )
    if not result.is_command and result.should_enter_chat_service:
        return None
    if not result.should_reply:
        return ChatResponse(
            text="",
            provider="local",
            model="database-v2-relationship-policy",
            used_live_api=False,
            fallback_used=True,
            error=result.reason_code,
        )
    return ChatResponse(
        text=result.reply_text or "",
        provider="local",
        model="database-v2-platform-command",
        used_live_api=False,
        fallback_used=True,
        error=result.reason_code,
    )
