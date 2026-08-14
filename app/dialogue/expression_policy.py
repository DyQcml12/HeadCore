from __future__ import annotations

import re
import time

from app.dialogue.act_classifier import has_casual_marker, infer_emotion, is_technical_context
from app.dialogue.types import ExpressionSettings, ExpressionState, StickerDecision, VoiceDecision


STICKER_INTENT_MARKERS = {
    "celebrate": ["好耶", "太好了", "成功", "赢了", "开心", "哈哈", "笑死"],
    "tease": ["吐槽", "阴阳", "坏笑", "得意", "绷不住", "哼"],
    "support": ["难过", "委屈", "累", "想哭", "抱抱", "陪我"],
    "awkward": ["尴尬", "无语", "沉默", "啊这", "离谱"],
    "cute_react": ["在吗", "干嘛", "想你", "可爱", "嘿嘿"],
}
VOICE_COMPANION_MARKERS = ["陪我", "想听你", "你在吗", "说说话", "有点累", "睡不着"]
VOICE_SOFT_REQUEST_MARKERS = ["在吗", "干嘛呢", "说句话", "聊会", "想你"]
LOW_EXPRESSION_ACKS = {"嗯", "嗯。", "哦", "哦。", "好", "好。", "行", "行。", "..", "...", "。", "。。", "。。。"}
STICKER_INTENT_WEIGHTS = {
    "celebrate": 0.45,
    "tease": 0.45,
    "support": 0.45,
    "awkward": 0.45,
    "cute_react": 0.28,
    "neutral": 0.0,
}
STICKER_EMOTION_WEIGHTS = {
    "happy": 0.25,
    "angry": 0.22,
    "tease": 0.25,
    "comfort": 0.25,
    "surprised": 0.22,
    "neutral": 0.0,
}
_INTERNAL_THOUGHT_PATTERN = re.compile(
    r"<internal_thought(?:\s[^>]*)?>.*?</internal_thought\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)


def infer_sticker_intent(user_input: str, reply_text: str = "") -> str:
    text = user_input + " " + reply_text
    for intent, markers in STICKER_INTENT_MARKERS.items():
        if any(marker in text for marker in markers):
            return intent
    if len(user_input.strip()) <= 12:
        return "cute_react"
    return "neutral"


def sanitize_visible_reply(reply_text: str) -> str:
    """Defensively remove a model's disallowed internal-thought wrapper."""
    return _INTERNAL_THOUGHT_PATTERN.sub("", reply_text).strip()


def evaluate_sticker_decision(
    *,
    settings: ExpressionSettings,
    user_input: str,
    reply_text: str,
    state: ExpressionState,
    now: float | None = None,
) -> StickerDecision:
    emotion = infer_emotion(user_input, reply_text)
    intent = infer_sticker_intent(user_input, reply_text)
    reasons: list[str] = []
    if not settings.sticker_auto_reply_enabled:
        return StickerDecision(False, intent, emotion, 0.0, ["disabled"])
    if is_technical_context(user_input):
        return StickerDecision(False, intent, emotion, 0.0, ["technical_context"])
    if is_low_expression_ack(user_input) and emotion == "neutral":
        return StickerDecision(False, intent, emotion, 0.0, ["low_expression_ack"])
    current = now if now is not None else time.time()
    if current - state.last_sticker_at < settings.sticker_cooldown_seconds:
        return StickerDecision(False, intent, emotion, 0.0, ["cooldown_seconds"])
    if state.sticker_turns_since < settings.sticker_cooldown_messages:
        return StickerDecision(False, intent, emotion, 0.0, ["cooldown_messages"])

    score = 0.0
    intent_weight = STICKER_INTENT_WEIGHTS.get(intent, 0.0)
    if intent_weight:
        score += intent_weight
        reasons.append(f"intent:{intent}")
    emotion_weight = STICKER_EMOTION_WEIGHTS.get(emotion, 0.0)
    if emotion_weight:
        score += emotion_weight
        reasons.append(f"emotion:{emotion}")
    if has_casual_marker(user_input, reply_text):
        score += 0.17
        reasons.append("casual_marker")
    if 6 <= len(reply_text.strip()) <= 45:
        score += 0.1
        reasons.append("short_reply")
    if len(user_input.strip()) <= 16:
        score += 0.08
        reasons.append("short_input")
    if state.sticker_turns_since >= max(settings.sticker_cooldown_messages * 2, settings.sticker_cooldown_messages + 3):
        score += 0.05
        reasons.append("sticker_gap")
    if len(reply_text.strip()) < 4:
        score -= 0.25
        reasons.append("reply_too_short")

    score = max(0.0, min(1.0, score))
    threshold = sticker_expression_threshold(settings.sticker_auto_probability)
    return StickerDecision(score >= threshold, intent, emotion, score, reasons or ["low_expression_need"])


def evaluate_voice_decision(
    *,
    settings: ExpressionSettings,
    user_input: str,
    state: ExpressionState,
    now: float | None = None,
) -> VoiceDecision:
    if not settings.voice_auto_reply_enabled:
        return VoiceDecision(False, "none", 0.0, ["disabled"])
    if is_technical_context(user_input):
        return VoiceDecision(False, "none", 0.0, ["technical_context"])
    if is_low_expression_ack(user_input):
        return VoiceDecision(False, "none", 0.0, ["low_expression_ack"])
    current = now if now is not None else time.time()
    if current - state.last_voice_at < settings.voice_cooldown_seconds:
        return VoiceDecision(False, "none", 0.0, ["cooldown_seconds"])
    if state.voice_turns_since < settings.voice_cooldown_messages:
        return VoiceDecision(False, "none", 0.0, ["cooldown_messages"])

    emotion = infer_emotion(user_input)
    score = 0.0
    reasons: list[str] = []
    if any(marker in user_input for marker in VOICE_COMPANION_MARKERS):
        score += 0.42
        reasons.append("companion_intent")
    if any(marker in user_input for marker in VOICE_SOFT_REQUEST_MARKERS):
        score += 0.22
        reasons.append("soft_voice_context")
    if emotion == "comfort":
        score += 0.28
        reasons.append("emotion:comfort")
    elif emotion in {"happy", "tease", "surprised"}:
        score += 0.2
        reasons.append(f"emotion:{emotion}")
    if len(user_input.strip()) <= 18:
        score += 0.08
        reasons.append("short_input")
    if state.voice_turns_since >= max(settings.voice_cooldown_messages * 2, settings.voice_cooldown_messages + 4):
        score += 0.05
        reasons.append("voice_gap")

    score = max(0.0, min(1.0, score))
    style = infer_voice_style(emotion, score)
    threshold = voice_expression_threshold(settings.voice_auto_probability)
    return VoiceDecision(score >= threshold, style if score >= threshold else "none", score, reasons or ["low_voice_need"])


def deterministic_score(text: str) -> float:
    value = 2166136261
    for char in text:
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    return value / 0xFFFFFFFF


def is_low_expression_ack(user_input: str) -> bool:
    compact = "".join(user_input.strip().split())
    return compact in LOW_EXPRESSION_ACKS


def sticker_expression_threshold(sensitivity: float) -> float:
    bounded = max(0.0, min(1.0, sensitivity))
    return 0.56 - bounded * 0.16


def voice_expression_threshold(sensitivity: float) -> float:
    bounded = max(0.0, min(1.0, sensitivity))
    return 0.64 - bounded * 0.14


def infer_voice_style(emotion: str, score: float) -> str:
    if emotion == "comfort":
        return "comfort"
    if emotion in {"happy", "surprised"} and score >= 0.7:
        return "playful"
    return "soft"
