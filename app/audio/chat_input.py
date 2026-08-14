from __future__ import annotations

import re
from dataclasses import dataclass

from app.audio.schemas import AsrFileResponse


CLARIFICATION_REPLY = "我刚才没听清，你短一点再说一遍。"
MAX_AUDIO_CHAT_CHARS = 80
CLARIFY_QUALITY_REASONS = {
    "empty_transcript",
    "too_short",
    "low_chinese_ratio",
    "mojibake_or_replacement_char",
    "excessive_repetition",
    "punctuation_only",
    "engine_error",
}


@dataclass(frozen=True)
class PreparedAudioChatInput:
    text: str
    should_clarify: bool
    clarify_reasons: list[str]
    clarification_reply: str = CLARIFICATION_REPLY


def clean_asr_text_for_chat(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = cleaned.replace("？，", "？").replace("，？", "？")
    cleaned = cleaned.replace("！，", "！").replace("，！", "！")
    cleaned = cleaned.replace("。，", "。").replace("，。", "。")
    cleaned = re.sub(r"[，,、；;：:。！？!?]{2,}", "。", cleaned)
    return cleaned


def prepare_audio_chat_input(asr: AsrFileResponse) -> PreparedAudioChatInput:
    cleaned = clean_asr_text_for_chat(asr.text)
    reasons = clarify_reasons_for_audio_chat(
        text=cleaned,
        quality_passed=asr.quality_passed,
        quality_reasons=asr.quality_reasons,
    )
    return PreparedAudioChatInput(
        text=cleaned,
        should_clarify=bool(reasons),
        clarify_reasons=reasons,
    )


def clarify_reasons_for_audio_chat(
    *,
    text: str,
    quality_passed: bool,
    quality_reasons: list[str],
) -> list[str]:
    reasons: list[str] = []
    if not text:
        reasons.append("empty_after_cleaning")
    if len(text) > MAX_AUDIO_CHAT_CHARS:
        reasons.append("too_long_for_realtime_chat")
    if not quality_passed:
        blocking_reasons = [
            reason for reason in quality_reasons if reason in CLARIFY_QUALITY_REASONS
        ]
        reasons.extend(blocking_reasons)
    return list(dict.fromkeys(reasons))
