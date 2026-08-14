from __future__ import annotations

from dataclasses import dataclass

from app.mind.conversation_state import ConversationState


@dataclass(frozen=True)
class SelfState:
    mood: str
    energy: str
    focus: str
    tension: str
    instruction: str


def build_self_state(conversation: ConversationState) -> SelfState:
    if conversation.should_deescalate:
        mood = "calm_attentive"
        energy = "low_to_medium"
        tension = "elevated"
    elif conversation.current_topic == "short_casual":
        mood = "light"
        energy = "medium"
        tension = "low"
    elif conversation.current_topic == "technical_or_project":
        mood = "steady"
        energy = "medium"
        tension = "medium"
    else:
        mood = "natural"
        energy = "medium"
        tension = "low"
    focus = conversation.current_topic
    instruction = (
        "内部状态："
        f"mood={mood}，energy={energy}，focus={focus}，tension={tension}。"
        "这只是控制语气连续性的内部状态，不要向用户解释；回复要像延续上一轮的人。"
    )
    return SelfState(
        mood=mood,
        energy=energy,
        focus=focus,
        tension=tension,
        instruction=instruction,
    )


def build_mind_state_instruction(conversation: ConversationState) -> str:
    self_state = build_self_state(conversation)
    return conversation.instruction + "\n" + self_state.instruction
