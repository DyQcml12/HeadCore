from __future__ import annotations

from dataclasses import replace

from app.channels.contracts import (
    ChannelCapabilitySet,
    ChannelEvent,
    ChannelResponse,
    ChannelResponsePart,
    ChannelThreadType,
    ResponsePartKind,
)
from app.providers.contracts import Provider, ProviderCapability, ProviderHealth

from .models import DeliveryContext, PlatformCapabilities, ResponseBundle, VoiceStatus
from .planner import ExpressionRequest


def capabilities_from_channel(
    capabilities: ChannelCapabilitySet,
    *,
    voice_in_group: bool = False,
    max_voice_segments: int | None = None,
) -> PlatformCapabilities:
    return PlatformCapabilities(
        voice=capabilities.native_voice or capabilities.audio_attachment,
        stickers=capabilities.image,
        attachments=capabilities.file,
        voice_in_group=voice_in_group,
        max_voice_segments=max_voice_segments,
    )


def delivery_context_from_event(
    event: ChannelEvent,
    *,
    is_owner: bool,
) -> DeliveryContext:
    return DeliveryContext(
        is_owner=is_owner,
        is_group=event.thread.thread_type == ChannelThreadType.GROUP,
    )


def provider_supports_tts(provider: Provider, health: ProviderHealth) -> bool:
    return (
        ProviderCapability.TTS in provider.capabilities
        and health in {ProviderHealth.HEALTHY, ProviderHealth.DEGRADED}
    )


def with_provider_capability(
    request: ExpressionRequest,
    provider: Provider,
    health: ProviderHealth,
) -> ExpressionRequest:
    return replace(request, provider_voice_capable=provider_supports_tts(provider, health))


def response_bundle_to_channel_response(
    bundle: ResponseBundle,
    capabilities: ChannelCapabilitySet,
    *,
    reply_to_message_id: str | None = None,
) -> ChannelResponse:
    parts: list[ChannelResponsePart] = []
    if not bundle.delivery.suppress_display_text:
        parts.append(ChannelResponsePart(kind=ResponsePartKind.TEXT, content=bundle.display_text))

    if bundle.voice.status == VoiceStatus.READY and bundle.voice.output_path is not None:
        if capabilities.native_voice:
            voice_kind = ResponsePartKind.NATIVE_VOICE
        elif capabilities.audio_attachment:
            voice_kind = ResponsePartKind.AUDIO_ATTACHMENT
        else:
            raise ValueError("ready voice bundle requires a voice-capable channel")
        parts.append(
            ChannelResponsePart(
                kind=voice_kind,
                content=str(bundle.voice.output_path),
                media_type=f"audio/{bundle.voice.audio_format}",
            )
        )

    if bundle.sticker.should_send:
        if not capabilities.image:
            raise ValueError("sendable sticker plan requires image capability")
        parts.append(ChannelResponsePart(kind=ResponsePartKind.IMAGE, content=bundle.sticker.asset_id))

    if bundle.delivery.attachment_paths:
        if not capabilities.file:
            raise ValueError("planned attachments require file capability")
        parts.extend(
            ChannelResponsePart(kind=ResponsePartKind.FILE, content=str(path))
            for path in bundle.delivery.attachment_paths
        )

    return ChannelResponse(parts=tuple(parts), reply_to_message_id=reply_to_message_id)
