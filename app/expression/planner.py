from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from app.dialogue.types import StickerDecision, VoiceDecision

from .models import (
    DeliveryContext,
    DeliveryFallback,
    DeliveryHints,
    FallbackReason,
    PlatformCapabilities,
    ResponseBundle,
    StickerPlan,
    VoicePlan,
    VoiceStatus,
)


SUPPORTED_VOICE_FORMATS = frozenset({"wav", "mp3", "ogg", "opus"})
_SAFE_DETAIL_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")


@dataclass(frozen=True)
class ExpressionRequest:
    display_text: str
    voice_requested: bool = False
    voice_segments: tuple[str, ...] = ()
    voice_format: str = "wav"
    voice_owner_only: bool = False
    provider_voice_capable: bool = False
    sticker_requested: bool = False
    sticker_asset_id: str | None = None
    sticker_intent: str = "neutral"
    sticker_cooldown_allowed: bool = True
    attachment_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if not self.display_text.strip():
            raise ValueError("display_text must not be blank")
        if self.voice_requested and not self.voice_segments:
            raise ValueError("voice_segments are required when voice is requested")
        normalized_format = self.voice_format.strip().lower()
        if normalized_format not in SUPPORTED_VOICE_FORMATS:
            raise ValueError("voice_format is unsupported")
        object.__setattr__(self, "voice_format", normalized_format)


def request_from_dialogue_decisions(
    *,
    display_text: str,
    voice: VoiceDecision,
    sticker: StickerDecision,
    sticker_asset_id: str | None = None,
    provider_voice_capable: bool = False,
    voice_owner_only: bool = False,
) -> ExpressionRequest:
    return ExpressionRequest(
        display_text=display_text,
        voice_requested=voice.should_send,
        voice_segments=(display_text,) if voice.should_send else (),
        voice_owner_only=voice_owner_only,
        provider_voice_capable=provider_voice_capable,
        sticker_requested=sticker.should_send,
        sticker_asset_id=sticker_asset_id,
        sticker_intent=sticker.intent,
        sticker_cooldown_allowed="cooldown_seconds" not in sticker.reasons
        and "cooldown_messages" not in sticker.reasons,
    )


class ExpressionPlanner:
    def plan(
        self,
        request: ExpressionRequest,
        *,
        context: DeliveryContext,
        capabilities: PlatformCapabilities,
        controlled_media_root: Path | None = None,
    ) -> ResponseBundle:
        fallbacks: list[DeliveryFallback] = []
        voice = self._plan_voice(request, context, capabilities, fallbacks)
        sticker = self._plan_sticker(request, capabilities, fallbacks)
        attachments = self._plan_attachments(
            request.attachment_paths,
            capabilities,
            controlled_media_root,
            fallbacks,
        )
        return ResponseBundle(
            display_text=request.display_text,
            voice=voice,
            sticker=sticker,
            delivery=DeliveryHints(attachment_paths=attachments),
            fallbacks=tuple(fallbacks),
        )

    def finalize_voice(
        self,
        bundle: ResponseBundle,
        *,
        output_path: Path | None,
        controlled_media_root: Path,
        error_detail: str | None = None,
    ) -> ResponseBundle:
        if bundle.voice.status is not VoiceStatus.PENDING:
            raise ValueError("voice plan is not pending")
        if output_path is None:
            return self._voice_fallback(
                bundle,
                FallbackReason.VOICE_TTS_FAILED,
                _safe_fallback_detail(error_detail),
            )
        if not _is_controlled_absolute_path(output_path, controlled_media_root):
            return self._voice_fallback(bundle, FallbackReason.MEDIA_PATH_INVALID)
        voice = replace(bundle.voice, status=VoiceStatus.READY, output_path=output_path.resolve())
        delivery = replace(bundle.delivery, suppress_display_text=True)
        return replace(bundle, voice=voice, delivery=delivery)

    @staticmethod
    def _plan_voice(
        request: ExpressionRequest,
        context: DeliveryContext,
        capabilities: PlatformCapabilities,
        fallbacks: list[DeliveryFallback],
    ) -> VoicePlan:
        if not request.voice_requested:
            return VoicePlan()
        reason: FallbackReason | None = None
        if request.voice_owner_only and not context.is_owner:
            reason = FallbackReason.VOICE_OWNER_REQUIRED
        elif context.is_group and not capabilities.voice_in_group:
            reason = FallbackReason.VOICE_GROUP_UNSUPPORTED
        elif not capabilities.voice:
            reason = FallbackReason.VOICE_CAPABILITY_UNSUPPORTED
        elif not request.provider_voice_capable:
            reason = FallbackReason.VOICE_PROVIDER_UNAVAILABLE

        segments = request.voice_segments
        if reason is None and capabilities.max_voice_segments is not None:
            if len(segments) > capabilities.max_voice_segments:
                reason = FallbackReason.PLATFORM_LIMIT
        if reason is not None:
            fallbacks.append(DeliveryFallback(reason))
            status = VoiceStatus.FALLBACK_TO_TEXT
        else:
            status = VoiceStatus.PENDING
        return VoicePlan(
            status=status,
            provider_capable=request.provider_voice_capable,
            segments=segments,
            audio_format=request.voice_format,
            owner_only=request.voice_owner_only,
        )

    @staticmethod
    def _plan_sticker(
        request: ExpressionRequest,
        capabilities: PlatformCapabilities,
        fallbacks: list[DeliveryFallback],
    ) -> StickerPlan:
        if request.sticker_requested and not request.sticker_cooldown_allowed:
            fallbacks.append(DeliveryFallback(FallbackReason.STICKER_COOLDOWN))
        elif request.sticker_requested and not capabilities.stickers:
            fallbacks.append(DeliveryFallback(FallbackReason.STICKER_CAPABILITY_UNSUPPORTED))
        elif request.sticker_requested and not request.sticker_asset_id:
            fallbacks.append(DeliveryFallback(FallbackReason.STICKER_ASSET_MISSING))
        return StickerPlan(
            requested=(
                request.sticker_requested
                and capabilities.stickers
                and request.sticker_asset_id is not None
            ),
            asset_id=request.sticker_asset_id,
            intent=request.sticker_intent,
            cooldown_allowed=request.sticker_cooldown_allowed,
        )

    @staticmethod
    def _plan_attachments(
        paths: tuple[Path, ...],
        capabilities: PlatformCapabilities,
        controlled_media_root: Path | None,
        fallbacks: list[DeliveryFallback],
    ) -> tuple[Path, ...]:
        if not paths:
            return ()
        if not capabilities.attachments:
            fallbacks.append(DeliveryFallback(FallbackReason.ATTACHMENT_CAPABILITY_UNSUPPORTED))
            return ()
        if controlled_media_root is None or any(
            not _is_controlled_absolute_path(path, controlled_media_root) for path in paths
        ):
            fallbacks.append(DeliveryFallback(FallbackReason.MEDIA_PATH_INVALID))
            return ()
        return tuple(path.resolve() for path in paths)

    @staticmethod
    def _voice_fallback(
        bundle: ResponseBundle,
        reason: FallbackReason,
        detail: str | None = None,
    ) -> ResponseBundle:
        voice = replace(bundle.voice, status=VoiceStatus.FALLBACK_TO_TEXT, output_path=None)
        delivery = replace(bundle.delivery, suppress_display_text=False)
        return replace(
            bundle,
            voice=voice,
            delivery=delivery,
            fallbacks=(*bundle.fallbacks, DeliveryFallback(reason, detail)),
        )


def _is_controlled_absolute_path(path: Path, controlled_root: Path) -> bool:
    if not path.is_absolute() or not controlled_root.is_absolute():
        return False
    try:
        path.resolve().relative_to(controlled_root.resolve())
    except ValueError:
        return False
    return True


def _safe_fallback_detail(detail: str | None) -> str | None:
    if detail is None:
        return None
    normalized = detail.strip().lower()
    return normalized if _SAFE_DETAIL_PATTERN.fullmatch(normalized) else None
