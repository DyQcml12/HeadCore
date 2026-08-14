from __future__ import annotations

from dataclasses import dataclass

from app.persona.relationship_roles import canonical_relationship_role


@dataclass(frozen=True)
class TonePolicy:
    role: str
    warmth: str
    tease_level: str
    intimacy_level: str
    max_default_sentences: int
    instruction: str


def build_tone_policy(role: str) -> TonePolicy:
    normalized = canonical_relationship_role(role)
    if normalized == "admin_partner":
        return TonePolicy(
            role="admin_partner",
            warmth="high",
            tease_level="light",
            intimacy_level="high_but_bounded",
            max_default_sentences=2,
            instruction=(
                "人际语气：当前是管理员/爱人。可以更熟悉、更偏心、轻微互怼，"
                "像亲近的人自然接话；但不要恋爱脑、占有欲、过度承诺或长篇撒娇。"
                "用户嫌怪时立刻收敛。"
            ),
        )
    if normalized == "normal_friend":
        return TonePolicy(
            role="normal_friend",
            warmth="medium_low",
            tease_level="very_light",
            intimacy_level="low",
            max_default_sentences=2,
            instruction=(
                "人际语气：当前是普通朋友或相关联系人。可以自然友好地闲聊，"
                "但不要突然暧昧、不要过度亲密，不拿身份关系开重玩笑。"
            ),
        )
    if normalized == "blocked":
        return TonePolicy(
            role="blocked",
            warmth="none",
            tease_level="none",
            intimacy_level="none",
            max_default_sentences=1,
            instruction="人际语气：当前对象被阻断。只给最短边界回复，不继续展开。",
        )


def build_tone_policy_instruction(role: str) -> str:
    return build_tone_policy(role).instruction
