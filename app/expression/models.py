from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path


class FallbackReason(str, Enum):
    VOICE_OWNER_REQUIRED = "voice_owner_required"
    VOICE_GROUP_UNSUPPORTED = "voice_group_unsupported"
    VOICE_PROVIDER_UNAVAILABLE = "voice_provider_unavailable"
    VOICE_CAPABILITY_UNSUPPORTED = "voice_capability_unsupported"
    VOICE_TTS_FAILED = "voice_tts_failed"
    STICKER_COOLDOWN = "sticker_cooldown"
    STICKER_ASSET_MISSING = "sticker_asset_missing"
    STICKER_CAPABILITY_UNSUPPORTED = "sticker_capability_unsupported"
    ATTACHMENT_CAPABILITY_UNSUPPORTED = "attachment_capability_unsupported"
    PLATFORM_LIMIT = "platform_limit"
    MEDIA_PATH_INVALID = "media_path_invalid"


class VoiceStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    READY = "ready"
    FALLBACK_TO_TEXT = "fallback_to_text"


@dataclass(frozen=True)
class PlatformCapabilities:
    voice: bool = False
    stickers: bool = False
    attachments: bool = False
    voice_in_group: bool = False
    max_voice_segments: int | None = None

    def __post_init__(self) -> None:
        if self.max_voice_segments is not None and self.max_voice_segments < 1:
            raise ValueError("max_voice_segments must be positive")


@dataclass(frozen=True)
class DeliveryContext:
    is_owner: bool = False
    is_group: bool = False


@dataclass(frozen=True)
class DeliveryFallback:
    reason: FallbackReason
    detail: str | None = None


@dataclass(frozen=True)
class VoicePlan:
    status: VoiceStatus = VoiceStatus.NOT_REQUESTED
    provider_capable: bool = False
    segments: tuple[str, ...] = ()
    audio_format: str = "wav"
    owner_only: bool = False
    output_path: Path | None = None

    def __post_init__(self) -> None:
        if self.status is VoiceStatus.READY:
            if self.output_path is None or not self.output_path.is_absolute():
                raise ValueError("ready voice requires an absolute output_path")
        elif self.output_path is not None:
            raise ValueError("output_path is only valid for ready voice")

    @property
    def should_synthesize(self) -> bool:
        return self.status is VoiceStatus.PENDING


@dataclass(frozen=True)
class StickerPlan:
    requested: bool = False
    asset_id: str | None = None
    intent: str = "neutral"
    cooldown_allowed: bool = True

    @property
    def should_send(self) -> bool:
        return self.requested and self.cooldown_allowed and self.asset_id is not None


@dataclass(frozen=True)
class DeliveryHints:
    suppress_display_text: bool = False
    attachment_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ResponseBundle:
    display_text: str
    voice: VoicePlan = field(default_factory=VoicePlan)
    sticker: StickerPlan = field(default_factory=StickerPlan)
    delivery: DeliveryHints = field(default_factory=DeliveryHints)
    fallbacks: tuple[DeliveryFallback, ...] = ()

    def __post_init__(self) -> None:
        if self.delivery.suppress_display_text and self.voice.status is not VoiceStatus.READY:
            raise ValueError("display text can only be suppressed for ready voice")

    def with_fallback(self, fallback: DeliveryFallback) -> ResponseBundle:
        return replace(self, fallbacks=(*self.fallbacks, fallback))
