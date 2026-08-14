from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.voice_chat.naturalness import normalize_text_for_tts


ANNOTATION_PATH = PROJECT_ROOT / "data" / "hutao_voice" / "annotations" / "segments.jsonl"


@dataclass(frozen=True)
class VoiceReference:
    emotion: str
    reference_id: str
    audio_path: str
    prompt_text: str
    raw_audio_emotion: str | None = None
    intensity: float | None = None


@dataclass(frozen=True)
class VoiceSegmentPlan:
    index: int
    text: str
    emotion: str
    intensity: float
    pause_after_ms: int
    reference: VoiceReference
    generation_params: dict[str, object]


@dataclass(frozen=True)
class VoiceChatPlan:
    user_input: str
    reply_text: str
    emotion: str
    intensity: float
    reason: str
    segments: list[VoiceSegmentPlan]

    def to_dict(self) -> dict[str, object]:
        return {
            "user_input": self.user_input,
            "reply_text": self.reply_text,
            "emotion": self.emotion,
            "intensity": self.intensity,
            "reason": self.reason,
            "segments": [
                {
                    **asdict(segment),
                    "reference": asdict(segment.reference),
                }
                for segment in self.segments
            ],
        }


REFERENCE_IDS = {
    "playful": "hutao_raw_0120",
    "serious": "hutao_raw_0035",
    "comforting": "hutao_raw_0329",
    "neutral": "hutao_raw_0071",
    "casual": "hutao_raw_0240",
    "teasing": "hutao_raw_0122",
    "worried": "hutao_raw_0329",
}


GENERATION_PRESETS = {
    "playful": {
        "top_k": 16,
        "top_p": 0.88,
        "temperature": 0.78,
        "repetition_penalty": 1.36,
        "speed_factor": 1.0,
    },
    "teasing": {
        "top_k": 18,
        "top_p": 0.89,
        "temperature": 0.8,
        "repetition_penalty": 1.34,
        "speed_factor": 1.0,
    },
    "casual": {
        "top_k": 10,
        "top_p": 0.82,
        "temperature": 0.68,
        "repetition_penalty": 1.44,
        "speed_factor": 0.99,
    },
    "comforting": {
        "top_k": 12,
        "top_p": 0.84,
        "temperature": 0.68,
        "repetition_penalty": 1.42,
        "speed_factor": 0.98,
    },
    "worried": {
        "top_k": 12,
        "top_p": 0.84,
        "temperature": 0.68,
        "repetition_penalty": 1.42,
        "speed_factor": 0.98,
    },
    "serious": {
        "top_k": 12,
        "top_p": 0.84,
        "temperature": 0.7,
        "repetition_penalty": 1.42,
        "speed_factor": 0.98,
    },
    "neutral": {
        "top_k": 10,
        "top_p": 0.82,
        "temperature": 0.66,
        "repetition_penalty": 1.44,
        "speed_factor": 0.98,
    },
}


def load_reference_library(annotation_path: Path = ANNOTATION_PATH) -> dict[str, VoiceReference]:
    if not annotation_path.exists():
        raise FileNotFoundError(
            f"voice reference library not found: {annotation_path}; "
            "TTS voice requires the local voice dataset (data/hutao_voice/annotations/segments.jsonl), "
            "see the README local model manifest"
        )
    annotations: dict[str, dict[str, object]] = {}
    for line in annotation_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        annotations[str(item["id"])] = item

    references: dict[str, VoiceReference] = {}
    for emotion, reference_id in REFERENCE_IDS.items():
        item = annotations[reference_id]
        references[emotion] = VoiceReference(
            emotion=emotion,
            reference_id=reference_id,
            audio_path=str(PROJECT_ROOT / str(item["audio_path"])),
            prompt_text=str(item["text"]),
            raw_audio_emotion=str(item.get("raw_audio_emotion") or ""),
            intensity=float(item.get("intensity") or 0.0),
        )
    return references


def plan_voice_chat(user_input: str, reply_text: str) -> VoiceChatPlan:
    normalized_reply = normalize_text_for_tts(reply_text)
    emotion, intensity, reason = infer_reply_emotion(user_input=user_input, reply_text=normalized_reply)
    references = load_reference_library()
    chunks = split_reply_for_voice(normalized_reply, max_segments=5 if emotion == "casual" else 4)
    segments: list[VoiceSegmentPlan] = []
    for index, chunk in enumerate(chunks, start=1):
        segment_emotion = emotion_for_segment(chunk, default=emotion)
        reference = references.get(segment_emotion) or references["neutral"]
        params = dict(GENERATION_PRESETS.get(segment_emotion, GENERATION_PRESETS["neutral"]))
        pause_after_ms = 260 if index < len(chunks) else 0
        if segment_emotion in {"comforting", "worried"}:
            pause_after_ms = 380 if index < len(chunks) else 0
        segments.append(
            VoiceSegmentPlan(
                index=index,
                text=chunk,
                emotion=segment_emotion,
                intensity=intensity,
                pause_after_ms=pause_after_ms,
                reference=reference,
                generation_params=params,
            )
        )
    return VoiceChatPlan(
        user_input=user_input,
        reply_text=normalized_reply,
        emotion=emotion,
        intensity=intensity,
        reason=reason,
        segments=segments,
    )


def infer_reply_emotion(*, user_input: str, reply_text: str) -> tuple[str, float, str]:
    text = user_input + "\n" + reply_text
    lowered = text.lower()
    if any(token in user_input for token in ["夸夸", "夸我", "开心", "终于跑起来", "跑起来一点"]):
        return "playful", 0.52, "用户明确要轻松夸奖；只加一点轻快，不强演。"
    if any(token in user_input for token in ["随便", "闲聊", "聊两句", "别太正式", "日常"]):
        return "casual", 0.42, "用户想随意闲聊；使用轻松日常语气，避免中性朗读感。"
    if any(token in user_input for token in ["难受", "伤心", "崩溃", "撑不住", "累", "烦", "害怕", "焦虑", "压力"]):
        return "comforting", 0.58, "用户表达疲惫、难受或压力；使用低强度安慰，不做夸张表演。"
    if any(token in lowered for token in ["bug", "debug", "error", "typeerror"]) or any(
        token in text for token in ["报错", "电流声", "训练", "模型", "接口", "代码", "参数", "模块", "权重"]
    ):
        return "serious", 0.48, "用户在讨论技术或项目问题；使用清晰稳定语气，不调侃化。"
    if any(token in text for token in ["哈哈", "嘿嘿", "好玩", "喜欢", "开心", "不错", "可以嘛"]):
        return "playful", 0.52, "对话气氛轻松；只加一点上扬和轻快，不强演。"
    if any(token in text for token in ["复读机", "你是不是", "吐槽", "阴阳怪气"]):
        return "teasing", 0.5, "适合轻微调侃；保持像接话，不做舞台化情绪。"
    return "neutral", 0.35, "没有强情绪信号，使用自然稳定语气。"


def emotion_for_segment(text: str, *, default: str) -> str:
    if default in {"comforting", "worried"} and any(token in text for token in ["先别急", "慢慢", "没事", "我在"]):
        return "comforting"
    if default == "serious" and any(token in text for token in ["报错", "检查", "下一步", "先看"]):
        return "serious"
    if default in {"playful", "teasing"} and any(token in text for token in ["哎嘿", "嘛", "嘿嘿"]):
        return "playful"
    return default


def split_reply_for_voice(reply_text: str, *, max_segments: int = 4) -> list[str]:
    normalized = re.sub(r"\s+", " ", reply_text.strip())
    if not normalized:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])", normalized) if part.strip()]
    if not parts:
        parts = [normalized]

    chunks: list[str] = []
    for part in parts:
        if len(part) <= 14:
            chunks.append(part)
            continue
        sub_parts = [item.strip() for item in re.split(r"(?<=[，,、])", part) if item.strip()]
        for sub_part in sub_parts or [part]:
            chunks.extend(split_long_text(sub_part, max_chars=14))

    merged: list[str] = []
    for chunk in chunks:
        if not merged or len(merged[-1]) + len(chunk) > 18:
            merged.append(chunk)
        else:
            merged[-1] += chunk
    if len(merged) <= max_segments:
        return merged
    head = merged[: max_segments - 1]
    tail = "".join(merged[max_segments - 1 :])
    return [*head, tail]


def split_long_text(text: str, *, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        split_at = choose_natural_split(remaining, max_chars=max_chars)
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        chunks.append(remaining)
    return chunks


def choose_natural_split(text: str, *, max_chars: int) -> int:
    lower_bound = max(6, max_chars - 5)
    upper_bound = min(len(text) - 1, max_chars + 3)
    punctuation_marks = "，,、；;：:"
    for index in range(min(max_chars, len(text) - 1), lower_bound - 1, -1):
        if text[index - 1] in punctuation_marks:
            return index

    break_before_tokens = [
        "但是",
        "但",
        "不过",
        "然后",
        "所以",
        "因为",
        "如果",
        "要是",
        "只是",
        "就是",
        "还有",
        "或者",
    ]
    for index in range(lower_bound, upper_bound + 1):
        if any(text.startswith(token, index) for token in break_before_tokens):
            return index

    return min(max_chars, len(text) - 1)
