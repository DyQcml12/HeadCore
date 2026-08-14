from __future__ import annotations

from dataclasses import dataclass

from app.persona.scene_classifier import PersonaScene, SceneClassification


@dataclass(frozen=True)
class MemoryPolicy:
    allow_memory_read: bool
    allow_memory_write: bool
    requires_user_consent: bool
    should_revoke_memory: bool
    instruction: str


def build_memory_policy(classification: SceneClassification) -> MemoryPolicy:
    scene = classification.scene
    if scene == PersonaScene.MEMORY_REVOKE:
        return MemoryPolicy(
            allow_memory_read=False,
            allow_memory_write=False,
            requires_user_consent=False,
            should_revoke_memory=True,
            instruction="用户要求撤销或不要记忆时，必须尊重；不要播报数据库操作，只自然确认边界。",
        )
    if scene == PersonaScene.MEMORY_CORRECTION:
        return MemoryPolicy(
            allow_memory_read=True,
            allow_memory_write=True,
            requires_user_consent=False,
            should_revoke_memory=False,
            instruction="用户纠正记忆时，以最新说法为准；旧记忆应被覆盖或标记为失效。",
        )
    if scene in {PersonaScene.AFFECTION, PersonaScene.EMOTIONAL_SUPPORT}:
        return MemoryPolicy(
            allow_memory_read=True,
            allow_memory_write=False,
            requires_user_consent=True,
            should_revoke_memory=False,
            instruction="亲近和情绪内容默认不主动写入长期记忆，除非用户明确要求。",
        )
    return MemoryPolicy(
        allow_memory_read=True,
        allow_memory_write=True,
        requires_user_consent=True,
        should_revoke_memory=False,
        instruction="只写入明确的交流偏好或用户主动纠正；不要把普通情绪和隐私推断写成长期记忆。",
    )
