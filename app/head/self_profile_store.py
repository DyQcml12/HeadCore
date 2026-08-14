from __future__ import annotations

from app.head.self_profile import (
    SELF_PROFILE_MEMORY_TYPE,
    SELF_PROFILE_SESSION_ID,
    SelfProfile,
    self_profile_from_json,
    self_profile_to_json,
)
from app.storage.chat_repository import ChatRepository


async def load_self_profile(
    repository: ChatRepository,
    *,
    user_id: str,
) -> SelfProfile | None:
    """Read the latest self profile; missing or corrupted content yields None."""
    records = await repository.list_memories(
        user_id=user_id,
        memory_types=[SELF_PROFILE_MEMORY_TYPE],
        limit=1,
    )
    if not records:
        return None
    return self_profile_from_json(records[-1].content)


async def save_self_profile(
    repository: ChatRepository,
    *,
    user_id: str,
    profile: SelfProfile,
) -> SelfProfile:
    """Persist a validated profile as a single new memory record.

    Write-only callers (reflection loop or explicit admin reset) are the only
    allowed writers; chat turns never write the profile directly.
    """
    await repository.save_memory(
        user_id=user_id,
        session_id=SELF_PROFILE_SESSION_ID,
        memory_type=SELF_PROFILE_MEMORY_TYPE,
        content=self_profile_to_json(profile),
        confidence=0.9,
    )
    return profile


async def reset_self_profile(
    repository: ChatRepository,
    *,
    user_id: str,
) -> int:
    """Delete every persisted self profile for the user; returns count."""
    records = await repository.list_memories(
        user_id=user_id,
        memory_types=[SELF_PROFILE_MEMORY_TYPE],
        limit=1000,
    )
    deleted = 0
    for record in records:
        if await repository.delete_memory(user_id=user_id, memory_id=record.id):
            deleted += 1
    return deleted
