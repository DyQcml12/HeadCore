from __future__ import annotations

from dataclasses import dataclass

from app.mind.conversation_state import ConversationState
from app.persona.relationship_roles import canonical_relationship_role
from app.persona.relationship_context import RelationshipContext
from app.storage.chat_repository import MessageRecord


@dataclass(frozen=True)
class SocialState:
    familiarity: str
    trust_band: str
    boundary_mode: str
    teasing_allowed: bool
    intimacy_allowed: bool
    instruction: str


def build_social_state(
    *,
    relationship: RelationshipContext,
    conversation: ConversationState,
    recent_messages: list[MessageRecord],
    user_input: str,
) -> SocialState:
    user_turn_count = sum(1 for message in recent_messages if message.role == "user") + 1
    role = canonical_relationship_role(relationship.role)
    if role == "admin_partner":
        familiarity = "admin_partner_deep_familiar"
        trust_band = "high"
        intimacy_allowed = True
    elif role == "normal_friend":
        familiarity = "normal_friend_bounded"
        trust_band = "medium"
        intimacy_allowed = False
    elif role == "blocked":
        familiarity = "blocked"
        trust_band = "none"
        intimacy_allowed = False
    else:
        familiarity = "normal_friend_bounded"
        trust_band = "medium"
        intimacy_allowed = False

    boundary_mode = infer_boundary_mode(
        role=role,
        conversation=conversation,
        user_input=user_input,
    )
    teasing_allowed = (
        boundary_mode == "normal"
        and role in {"admin_partner", "normal_friend"}
        and conversation.recent_user_mood != "vulnerable"
    )
    instruction = build_social_instruction(
        familiarity=familiarity,
        trust_band=trust_band,
        boundary_mode=boundary_mode,
        teasing_allowed=teasing_allowed,
        intimacy_allowed=intimacy_allowed,
        user_turn_count=user_turn_count,
    )
    return SocialState(
        familiarity=familiarity,
        trust_band=trust_band,
        boundary_mode=boundary_mode,
        teasing_allowed=teasing_allowed,
        intimacy_allowed=intimacy_allowed,
        instruction=instruction,
    )


def infer_boundary_mode(
    *,
    role: str,
    conversation: ConversationState,
    user_input: str,
) -> str:
    if role == "blocked":
        return "closed"
    if conversation.last_user_correction != "none" or conversation.should_deescalate:
        return "repairing"
    if contains_any(user_input, ("管理员", "爱人", "主人", "权限", "隐私", "喜欢谁", "聊天记录", "自己人")):
        return "privacy_guard"
    if conversation.recent_user_mood in {"vulnerable", "tired"}:
        return "soft_support"
    return "normal"


def build_social_instruction(
    *,
    familiarity: str,
    trust_band: str,
    boundary_mode: str,
    teasing_allowed: bool,
    intimacy_allowed: bool,
    user_turn_count: int,
) -> str:
    lines = [
        "社交状态："
        f"familiarity={familiarity}，trust={trust_band}，boundary={boundary_mode}，"
        f"user_turns_in_recent_window={user_turn_count}。"
    ]
    if familiarity == "normal_friend_bounded":
        lines.append("对方是普通朋友或相关联系人；自然一点，但不要管理员/爱人级亲密。")
    elif familiarity == "admin_partner_deep_familiar":
        lines.append("对方是管理员/爱人；可以更顺口、更偏心，但仍要尊重纠正和边界。")
    if boundary_mode == "repairing":
        lines.append("当前处于修复期：不要贫嘴，不开死亡或关系玩笑，先短句把语气放稳。")
    elif boundary_mode == "privacy_guard":
        lines.append("当前触及关系或隐私边界：只给自然边界回复，不透露、不猜测、不套近乎。")
    elif boundary_mode == "soft_support":
        lines.append("当前应轻支持：少玩梗，少建议，先接住感受。")
    lines.append(
        "允许轻微打趣。"
        if teasing_allowed
        else "本轮不主动打趣，不用阴阳怪气证明角色感。"
    )
    lines.append(
        "允许亲近表达，但不要占有或恋爱脑。"
        if intimacy_allowed
        else "本轮不使用暧昧、恋人、专属、自己人等亲密升级表达。"
    )
    return "".join(lines)


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
