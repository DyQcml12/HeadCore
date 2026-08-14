from __future__ import annotations

import re
from dataclasses import dataclass

from app.storage.chat_repository import MessageRecord


CONSISTENT_ANSWER_MARKERS = (
    "记得",
    "叫什么",
    "叫我",
    "称呼",
    "还记得",
    "是不是",
    "什么名字",
)


@dataclass(frozen=True)
class RepetitionSignal:
    repeat_count: int
    requires_consistent_core: bool
    avoid_verbatim_repeat: bool
    instruction: str


def build_repetition_signal(
    *,
    user_input: str,
    recent_messages: list[MessageRecord],
) -> RepetitionSignal:
    normalized_input = normalize_user_input(user_input)
    repeat_count = sum(
        1
        for message in recent_messages
        if message.role == "user" and normalize_user_input(message.content) == normalized_input
    )
    requires_consistent_core = contains_any(user_input, CONSISTENT_ANSWER_MARKERS)
    avoid_verbatim_repeat = repeat_count > 0 and not requires_consistent_core

    if repeat_count <= 0:
        instruction = "没有检测到近期重复提问，正常回答。"
    elif requires_consistent_core:
        instruction = (
            f"用户近期第 {repeat_count + 1} 次问同一类事实或记忆问题。核心答案必须和之前一致，"
            "但表达可以更短；不要为了新鲜感改口。"
        )
    elif repeat_count == 1:
        instruction = "用户刚重复问过一次。不要逐字复读上一轮，换个短说法接住。"
    else:
        instruction = (
            f"用户已经连续或近期多次重复这个问题，本轮要自然点明刚问过，"
            "再用一句短回复收住，不要显得不耐烦。"
        )

    return RepetitionSignal(
        repeat_count=repeat_count,
        requires_consistent_core=requires_consistent_core,
        avoid_verbatim_repeat=avoid_verbatim_repeat,
        instruction=instruction,
    )


def normalize_user_input(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"\s+", "", lowered)
    lowered = re.sub(r"[，。！？、,.!?~～…]+", "", lowered)
    return lowered


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
