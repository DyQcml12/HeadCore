from __future__ import annotations

from typing import Any, Protocol

from app.storage.v2_models import (
    PlatformName,
    RelationshipType,
    V2ChatMessage,
    V2PendingRelationshipClaim,
    V2PersonaContext,
    V2RecentChat,
    V2RelationshipContext,
)


DATABASE_V2_SCHEMA_VERSION = "v2.001_hutao_chat_core_schema"
DATABASE_V2_SCHEMA_DESCRIPTION = "HutaoChatCore hutao_chat_core identity/persona/chat schema"


class DatabaseV2Repository(Protocol):
    async def find_relationship_context(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        platform_group_id: str | None = None,
    ) -> V2RelationshipContext | None:
        """Resolve an existing identity without creating or updating database rows."""
        pass

    async def get_control_status_snapshot(
        self,
        *,
        required_tables: tuple[str, ...],
    ) -> dict[str, Any]:
        """Return schema, table, and singleton-admin readiness data."""
        pass

    async def get_admin_profile_snapshot(self) -> dict[str, Any] | None:
        """Return the singleton admin and its accounts without private values."""
        pass

    async def list_profile_snapshots(
        self,
        *,
        relationship_type: RelationshipType | None,
        verified: bool | None,
        platform: PlatformName | None,
        query: str,
        limit: int,
        cursor_updated_at: str | None,
        cursor_profile_id: str | None,
    ) -> list[dict[str, Any]]:
        """Return at most limit ordered profile summary snapshots."""
        pass

    async def get_profile_detail_snapshot(self, *, profile_id: str) -> dict[str, Any] | None:
        """Return an aggregate read-only profile detail snapshot."""
        pass

    async def update_profile_relationship(
        self,
        *,
        profile_id: str,
        relationship_type: RelationshipType,
        verified: bool,
        changed_by_profile_id: str,
        reason: str,
    ) -> dict[str, object]:
        """Update one existing profile relationship and record its audit event."""
        pass

    async def record_database_control_event(
        self,
        *,
        actor_profile_id: str,
        platform: str,
        command_name: str,
        status: str,
        reason_code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Record a redacted accepted/rejected/failed control-plane operation."""
        pass

    async def bootstrap_admin_if_missing(
        self,
        *,
        qq_ids: list[str],
        wechat_ids: list[str],
        display_name: str,
    ) -> str | None:
        """Create the singleton admin profile only when no admin exists."""
        pass

    async def resolve_relationship_context(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        platform_group_id: str | None = None,
        display_name: str = "",
    ) -> V2RelationshipContext:
        """Resolve or create profile/account and return runtime permissions."""
        pass

    async def ensure_default_personas(self) -> None:
        """Create database projection rows for the active persona registry profile."""
        pass

    async def resolve_persona_context(
        self,
        *,
        relationship_context: V2RelationshipContext,
        conversation_id: str | None = None,
        platform_thread_id: str | None = None,
    ) -> V2PersonaContext:
        """Resolve the active persona from conversation/profile/platform/default bindings."""
        pass

    async def set_relationship(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        relationship_type: RelationshipType,
        display_name: str = "",
        changed_by_profile_id: str | None = None,
        reason: str = "",
    ) -> V2RelationshipContext:
        """Admin-only operation to change profile-level relationship."""
        pass

    async def bind_accounts(
        self,
        *,
        source_platform: PlatformName,
        source_platform_user_id: str,
        target_platform: PlatformName,
        target_platform_user_id: str,
        changed_by_profile_id: str,
        reason: str = "",
    ) -> str:
        """Bind or merge two platform accounts into one profile."""
        pass

    async def list_recent_chats(self, *, limit: int = 10) -> list[V2RecentChat]:
        """Return recent conversations visible to the singleton admin."""
        pass

    async def list_chat_history(
        self,
        *,
        platform: PlatformName,
        platform_user_id: str,
        limit: int = 20,
    ) -> list[V2ChatMessage]:
        """Return recent admin-visible messages for one platform account/profile."""
        pass

    async def list_pending_relationship_claims(
        self,
        *,
        limit: int = 20,
    ) -> list[V2PendingRelationshipClaim]:
        """Return pending user self-claims for admin review."""
        pass

    async def approve_relationship_claim(
        self,
        *,
        claim_id: str,
        reviewed_by_profile_id: str,
    ) -> dict[str, object]:
        """Approve a user claim as verified portrait/social-label data."""
        pass

    async def reject_relationship_claim(
        self,
        *,
        claim_id: str,
        reviewed_by_profile_id: str,
    ) -> dict[str, object]:
        """Reject a user claim without changing relationship_type."""
        pass

    async def record_platform_command_event(
        self,
        *,
        message_id: str | None,
        actor_profile_id: str | None,
        command_name: str,
        platform: PlatformName,
        target_platform_user_id: str | None,
        status: str,
        reason_code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Persist an admin command audit event from a platform adapter."""
        pass
