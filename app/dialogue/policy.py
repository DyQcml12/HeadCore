from __future__ import annotations

import re

from app.dialogue.act_classifier import classify_dialogue_act, infer_emotion, is_technical_context
from app.dialogue.types import DialogueDecision


SHORT_QUESTION_MAX_CHARS = 18
SHORT_CHAT_MAX_CHARS = 72
QQ_REPLY_STYLE_INSTRUCTION = (
    "[QQ聊天回复要求]\n"
    "像真人私聊一样回复，不要写说明文。"
    "如果用户只是短句、问候、简单请求或闲聊，回复 1 句，最多 35 个中文字符。"
    "只有用户明确要求方案、步骤、代码、排查、训练或配置时，才可以分点展开。"
    "不要一次塞太多信息，不要每句都带设定解释。"
)


def build_dialogue_decision(user_input: str, *, channel: str = "api") -> DialogueDecision:
    stripped = user_input.strip()
    act = classify_dialogue_act(stripped)
    emotion = infer_emotion(stripped)
    reasons: list[str] = [f"act:{act}", f"emotion:{emotion}"]
    response_mode = "normal_chat"
    max_chars: int | None = None
    should_ask_followup = False
    prompt_instruction: str | None = None

    if act == "empty":
        response_mode = "micro_reply"
        max_chars = 24
        should_ask_followup = True
    elif act in {"technical_debug", "task_request"}:
        response_mode = "task_answer"
        max_chars = None
        reasons.append("task_context")
    elif act in {"affection", "casual_question", "celebration", "tease"}:
        response_mode = "short_chat"
        max_chars = 55 if channel == "qq" else 80
    elif act == "emotion_support":
        response_mode = "supportive"
        max_chars = 90
        should_ask_followup = True
    elif len(stripped) <= SHORT_QUESTION_MAX_CHARS and not is_technical_context(stripped):
        response_mode = "short_chat"
        max_chars = 55

    if channel == "qq" and response_mode in {"micro_reply", "short_chat", "supportive"}:
        prompt_instruction = QQ_REPLY_STYLE_INSTRUCTION

    return DialogueDecision(
        dialogue_act=act,
        emotion=emotion,
        response_mode=response_mode,
        max_chars=max_chars,
        should_ask_followup=should_ask_followup,
        prompt_instruction=prompt_instruction,
        reasons=reasons,
    )


def should_force_short_reply(user_input: str, *, channel: str = "qq") -> bool:
    decision = build_dialogue_decision(user_input, channel=channel)
    return decision.response_mode in {"micro_reply", "short_chat", "supportive"}


def build_response_style_instruction(user_input: str, *, channel: str = "qq") -> str | None:
    decision = build_dialogue_decision(user_input, channel=channel)
    return decision.prompt_instruction


def constrain_reply_text(text: str, *, user_input: str, max_chars: int | None = None, channel: str = "qq") -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    decision = build_dialogue_decision(user_input, channel=channel)
    limit = max_chars if max_chars is not None else decision.max_chars
    if decision.response_mode == "task_answer" or limit is None or len(cleaned) <= limit:
        return cleaned
    parts = [part for part in re.split(r"(?<=[。！？!?])", cleaned) if part.strip()]
    selected = ""
    for part in parts:
        if len(selected + part) <= limit:
            selected += part
            continue
        break
    if selected:
        return selected.strip()
    return cleaned[:limit].rstrip("，、；;：:。.!！?")

