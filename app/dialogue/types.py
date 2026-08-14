from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DialogueDecision:
    dialogue_act: str
    emotion: str
    response_mode: str
    max_chars: int | None
    should_ask_followup: bool
    prompt_instruction: str | None
    reasons: list[str]


@dataclass(frozen=True)
class ExpressionSettings:
    sticker_auto_reply_enabled: bool = True
    sticker_auto_probability: float = 0.18
    sticker_cooldown_messages: int = 4
    sticker_cooldown_seconds: float = 180.0
    voice_auto_reply_enabled: bool = False
    voice_auto_probability: float = 0.08
    voice_cooldown_messages: int = 8
    voice_cooldown_seconds: float = 600.0


@dataclass
class ExpressionState:
    last_sticker_at: float = 0.0
    last_voice_at: float = 0.0
    sticker_turns_since: int = 999
    voice_turns_since: int = 999
    recent_sticker_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StickerDecision:
    should_send: bool
    intent: str
    emotion: str
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class VoiceDecision:
    should_send: bool
    style: str
    score: float
    reasons: list[str]

