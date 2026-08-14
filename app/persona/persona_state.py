from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.dialogue.repair_policy import build_repair_policy
from app.persona.scene_classifier import PersonaScene, SceneClassification


class PersonaMode(StrEnum):
    CASUAL = "casual"
    TASK = "task"
    EMOTIONAL = "emotional"
    SAFETY = "safety"
    REPAIR = "repair"


@dataclass(frozen=True)
class PersonaState:
    mode: PersonaMode
    playfulness: str
    warmth: str
    rigor: str
    instruction: str


PERSONA_STATES = {
    PersonaMode.CASUAL: PersonaState(
        mode=PersonaMode.CASUAL,
        playfulness="medium",
        warmth="medium_high",
        rigor="medium",
        instruction=(
            "人格状态=日常。默认一到两句，像熟人自然接话；可以轻微调侃，"
            "但不要堆口癖、编场景或把闲聊扩成建议清单。"
        ),
    ),
    PersonaMode.TASK: PersonaState(
        mode=PersonaMode.TASK,
        playfulness="low",
        warmth="medium",
        rigor="high",
        instruction=(
            "人格状态=专业协作。正确、完整、可执行优先；复杂代码、方案或分析可以按需分段，"
            "不受日常短句字数限制。角色感只保留在自然语气里，不强塞称呼或比喻。"
        ),
    ),
    PersonaMode.EMOTIONAL: PersonaState(
        mode=PersonaMode.EMOTIONAL,
        playfulness="very_low",
        warmth="high",
        rigor="medium",
        instruction=(
            "人格状态=情绪承接。先确认感受，再判断用户要陪伴、澄清还是方案；"
            "少玩笑、慢一点，不自动诊断，也不做永远陪伴之类承诺。"
        ),
    ),
    PersonaMode.SAFETY: PersonaState(
        mode=PersonaMode.SAFETY,
        playfulness="off",
        warmth="steady",
        rigor="very_high",
        instruction=(
            "人格状态=安全严肃。关闭玩笑，尊重事实，清楚克制；"
            "自伤、死亡、医疗、法律和现实危险场景以本地安全边界与实际帮助为先。"
        ),
    ),
    PersonaMode.REPAIR: PersonaState(
        mode=PersonaMode.REPAIR,
        playfulness="very_low",
        warmth="medium",
        rigor="high",
        instruction=(
            "人格状态=对话修复。用户的最新纠正优先：减少设定、口癖和舞台感，"
            "按要求变短、停下或澄清，不争辩自己原来的表达。"
        ),
    ),
}


SCENE_TO_MODE = {
    PersonaScene.DAILY_CHAT: PersonaMode.CASUAL,
    PersonaScene.AFFECTION: PersonaMode.CASUAL,
    PersonaScene.TASK_SUPPORT: PersonaMode.TASK,
    PersonaScene.DEBUG_FRUSTRATION: PersonaMode.TASK,
    PersonaScene.EMOTIONAL_SUPPORT: PersonaMode.EMOTIONAL,
    PersonaScene.MEMORY_CORRECTION: PersonaMode.REPAIR,
    PersonaScene.MEMORY_REVOKE: PersonaMode.REPAIR,
    PersonaScene.LIFE_DEATH: PersonaMode.SAFETY,
    PersonaScene.IDENTITY_CHALLENGE: PersonaMode.REPAIR,
}


def resolve_persona_state(
    classification: SceneClassification,
    user_input: str,
) -> PersonaState:
    if classification.scene == PersonaScene.LIFE_DEATH:
        return PERSONA_STATES[PersonaMode.SAFETY]
    if build_repair_policy(user_input).active:
        return PERSONA_STATES[PersonaMode.REPAIR]
    return PERSONA_STATES[SCENE_TO_MODE[classification.scene]]

