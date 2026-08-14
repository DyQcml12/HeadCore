from __future__ import annotations

from dataclasses import dataclass

from app.dialogue.repair_policy import build_repair_policy
from app.storage.chat_repository import MessageRecord


MOOD_MARKERS = ("累", "烦", "难受", "崩溃", "焦虑", "委屈", "想哭")
TECHNICAL_MARKERS = ("debug", "bug", "报错", "代码", "项目", "模型", "训练", "接口", "数据库")
PRIVACY_MARKERS = ("主人", "权限", "关系", "隐私", "喜欢谁", "聊天记录")


@dataclass(frozen=True)
class ConversationState:
    current_topic: str
    last_user_correction: str
    recent_user_mood: str
    should_deescalate: bool
    instruction: str


def build_conversation_state(
    *,
    user_input: str,
    recent_messages: list[MessageRecord],
) -> ConversationState:
    user_turns = [message.content for message in recent_messages if message.role == "user"]
    latest_user_text = user_turns[-1] if user_turns else ""
    combined_recent = "\n".join(user_turns[-3:] + [user_input])
    repair = build_repair_policy(user_input)
    previous_repair = build_repair_policy(latest_user_text) if latest_user_text else repair
    last_user_correction = ",".join(repair.reasons or previous_repair.reasons)
    mood = infer_recent_user_mood(combined_recent)
    topic = infer_current_topic(user_input, latest_user_text)
    should_deescalate = repair.active or previous_repair.active or mood in {"frustrated", "vulnerable"}
    instruction = build_conversation_instruction(
        current_topic=topic,
        last_user_correction=last_user_correction,
        recent_user_mood=mood,
        should_deescalate=should_deescalate,
    )
    return ConversationState(
        current_topic=topic,
        last_user_correction=last_user_correction or "none",
        recent_user_mood=mood,
        should_deescalate=should_deescalate,
        instruction=instruction,
    )


def infer_current_topic(user_input: str, previous_user_input: str = "") -> str:
    text = user_input + "\n" + previous_user_input
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in TECHNICAL_MARKERS):
        return "technical_or_project"
    if any(marker in text for marker in PRIVACY_MARKERS):
        return "relationship_or_privacy"
    if any(marker in text for marker in MOOD_MARKERS):
        return "emotional_support"
    if len(user_input.strip()) <= 18:
        return "short_casual"
    return "general_chat"


def infer_recent_user_mood(text: str) -> str:
    if any(marker in text for marker in ("崩溃", "焦虑", "委屈", "想哭", "难受")):
        return "vulnerable"
    if any(marker in text for marker in ("烦", "气", "离谱", "别嘴臭", "别演")):
        return "frustrated"
    if any(marker in text for marker in ("开心", "好耶", "哈哈", "成功")):
        return "positive"
    if any(marker in text for marker in ("累", "困", "没劲")):
        return "tired"
    return "neutral"


def build_conversation_instruction(
    *,
    current_topic: str,
    last_user_correction: str,
    recent_user_mood: str,
    should_deescalate: bool,
) -> str:
    lines = [
        "共同语境：这不是第一次见面式回复；承接最近话题，不要重置成客服开场。",
        f"当前话题={current_topic}；用户近期状态={recent_user_mood}。",
    ]
    if last_user_correction:
        lines.append(
            "用户刚提出过体验纠正："
            + last_user_correction
            + "。下一轮必须体现改变，不要继续原来的怪味或攻击性。"
        )
    if should_deescalate:
        lines.append("当前应降温：短句、少设定、少反驳，先把话接稳。")
    return "".join(lines)
