from __future__ import annotations

import re


DIGIT_READINGS = {
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}

PERFORMANCE_CUE_PATTERN = re.compile(
    r"[（(【\[]\s*"
    r"(?:轻笑|笑|偷笑|叹气|叹息|小声|低声|认真|沉默|停顿|哼|咳|清嗓|坏笑|"
    r"挑眉|眨眼|挠头|捂脸|害羞|无奈|得意|温柔|疑惑|惊讶|生气|哭|抽泣)"
    r"\s*[）)】\]]"
)
LEADING_TTS_PUNCTUATION_PATTERN = re.compile(r"^[\s。！？!?，,、；;：:.．…~～-]+")


def strip_performance_cues(text: str) -> str:
    return PERFORMANCE_CUE_PATTERN.sub("", text)


def strip_leading_tts_punctuation(text: str) -> str:
    return LEADING_TTS_PUNCTUATION_PATTERN.sub("", text)


def normalize_reply_for_natural_chat(text: str) -> str:
    normalized = strip_performance_cues(text).strip()
    normalized = normalized.replace("～", "。").replace("~", "。")
    normalized = normalized.replace("——", "，").replace("—", "，")
    normalized = re.sub(r"[!！]{2,}", "！", normalized)
    normalized = re.sub(r"[。]{2,}", "。", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def normalize_text_for_tts(text: str) -> str:
    normalized = normalize_reply_for_natural_chat(text)
    normalized = normalized.replace("AI", "人工智能")
    normalized = normalized.replace("TTS", "语音合成")
    normalized = normalized.replace("bug", "问题")
    normalized = normalized.replace("debug", "调试")
    normalized = normalized.replace("Debug", "调试")
    normalized = re.sub(r"\d", lambda match: DIGIT_READINGS[match.group(0)], normalized)
    normalized = re.sub(r"[（）()【】\[\]「」『』]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = strip_leading_tts_punctuation(normalized)
    return normalized.strip()


def constrain_reply_for_realtime_tts(
    text: str,
    *,
    max_chars: int = 42,
    min_chars: int = 18,
) -> str:
    cleaned = normalize_reply_for_natural_chat(text)
    if len(cleaned) <= max_chars:
        return cleaned

    parts = [part for part in re.split(r"(?<=[。！？!?])", cleaned) if part.strip()]
    if not parts:
        return trim_to_natural_boundary(cleaned, max_chars=max_chars)

    selected = ""
    for part in parts:
        if len(selected + part) <= max_chars:
            selected += part
            continue
        remaining = max_chars - len(selected)
        if selected and len(selected) < min_chars and remaining >= 6:
            selected += trim_to_natural_boundary(part, max_chars=remaining)
        elif not selected:
            selected = trim_to_natural_boundary(part, max_chars=max_chars)
        break
    return selected or trim_to_natural_boundary(cleaned, max_chars=max_chars)


def trim_to_natural_boundary(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rstrip("，,、；;：:")
    for mark in ["，", "。", "？", "！", "、", ",", ";", "；", ":"]:
        index = clipped.rfind(mark)
        if index >= max(6, max_chars // 2):
            return clipped[: index + 1].rstrip("，,、；;：:")
    return clipped
