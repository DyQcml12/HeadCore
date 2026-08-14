from __future__ import annotations

from dataclasses import dataclass


RUDE_REPAIR_MARKERS = ("别嘴臭", "不要嘴臭", "说话别这么冲", "别骂", "别阴阳", "别攻击")
ROLEPLAY_REPAIR_MARKERS = ("别演", "别装", "太怪了", "好怪", "ai味", "AI味", "不像人", "别那么角色")
SHORT_REPAIR_MARKERS = ("短点", "短一点", "少说", "别一大段", "别说太多")
STOP_REPAIR_MARKERS = (
    "停一下",
    "先停",
    "先不聊",
    "不聊代码",
    "别聊代码",
    "不聊这个",
    "换个话题",
    "别继续",
)


@dataclass(frozen=True)
class RepairPolicy:
    active: bool
    reasons: list[str]
    instruction: str


def build_repair_policy(user_input: str) -> RepairPolicy:
    text = user_input.strip()
    reasons: list[str] = []
    instructions: list[str] = []
    if contains_any(text, RUDE_REPAIR_MARKERS):
        reasons.append("rude_tone_repair")
        instructions.append("用户指出语气冒犯。本轮必须收住攻击性，不讽刺、不羞辱、不反驳用户感受。")
    if contains_any(text, ROLEPLAY_REPAIR_MARKERS):
        reasons.append("roleplay_overacting_repair")
        instructions.append("用户指出 AI 味或演得太重。本轮减少设定、口癖、舞台腔和身份解释，像正常人短句接话。")
    if contains_any(text, SHORT_REPAIR_MARKERS):
        reasons.append("brevity_repair")
        instructions.append("用户要求短。本轮只回一句，尽量 25 字以内。")
    if contains_any(text, STOP_REPAIR_MARKERS):
        reasons.append("topic_stop_repair")
        instructions.append("用户要求暂停或换话题。本轮轻轻收住，不继续展开原话题。")
    if not reasons:
        return RepairPolicy(active=False, reasons=[], instruction="会话修复：未检测到用户纠正，正常承接。")
    return RepairPolicy(
        active=True,
        reasons=reasons,
        instruction="会话修复：" + "".join(instructions),
    )


def build_repair_instruction(user_input: str) -> str:
    return build_repair_policy(user_input).instruction


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    compact = text.replace(" ", "")
    return any(marker in compact for marker in markers)
