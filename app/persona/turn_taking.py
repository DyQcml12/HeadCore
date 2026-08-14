from __future__ import annotations

from dataclasses import dataclass


LOW_INFORMATION_INPUTS = {
    "嗯",
    "嗯。",
    "哦",
    "哦。",
    "好",
    "好。",
    "行",
    "行。",
    "随便",
    "随便。",
    "..",
    "...",
    "。。",
    "。。。",
}

SHORT_REPLY_MARKERS = (
    "少说",
    "短点",
    "短一点",
    "别解释太多",
    "别一大段",
    "别说太多",
    "收声",
)

PAUSE_MARKERS = (
    "停一下",
    "暂停",
    "先不聊",
    "不聊代码",
    "别聊代码",
    "到这",
    "闭嘴",
)

CONTINUE_MARKERS = (
    "继续",
    "下一步",
    "接着",
)

FATIGUE_MARKERS = (
    "累",
    "困",
    "烦",
    "没劲",
    "没动力",
)


@dataclass(frozen=True)
class TurnTakingSignal:
    low_information: bool
    asks_short_reply: bool
    pause_or_stop: bool
    asks_continue: bool
    fatigue_or_mood: bool
    max_chars: int
    instruction: str

    @property
    def should_minimize_reply(self) -> bool:
        return self.low_information or self.asks_short_reply or self.pause_or_stop


def classify_turn_taking(user_input: str) -> TurnTakingSignal:
    text = user_input.strip()
    compact = "".join(text.split())
    low_information = compact in LOW_INFORMATION_INPUTS
    asks_short_reply = contains_any(text, SHORT_REPLY_MARKERS)
    pause_or_stop = contains_any(text, PAUSE_MARKERS)
    asks_continue = contains_any(text, CONTINUE_MARKERS)
    fatigue_or_mood = contains_any(text, FATIGUE_MARKERS)

    max_chars = 50
    instructions: list[str] = []
    if low_information:
        max_chars = min(max_chars, 24)
        instructions.append("用户只给了低信息短回应，接一句就停，不要追问太多。")
    if asks_short_reply:
        max_chars = min(max_chars, 28)
        instructions.append("用户明确嫌话多，本轮必须短，最多一句。")
    if pause_or_stop:
        max_chars = min(max_chars, 24)
        instructions.append("用户在暂停或切换话题，轻轻收住，不要继续展开原话题。")
    if asks_continue and not asks_short_reply:
        max_chars = min(max_chars, 45)
        instructions.append("用户要推进下一步，直接给一个可执行动作，不要铺垫。")
    if fatigue_or_mood and not asks_short_reply:
        max_chars = min(max_chars, 35)
        instructions.append("用户状态偏累或烦，短接住情绪，不要长篇安慰。")
    if not instructions:
        instructions.append("按正常聊天节奏回复，默认一到两句。")

    return TurnTakingSignal(
        low_information=low_information,
        asks_short_reply=asks_short_reply,
        pause_or_stop=pause_or_stop,
        asks_continue=asks_continue,
        fatigue_or_mood=fatigue_or_mood,
        max_chars=max_chars,
        instruction=" ".join(instructions),
    )


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
