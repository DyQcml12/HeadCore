from __future__ import annotations

from app.channels.contracts import (
    ChannelCapabilitySet,
    ChannelPlatform,
    ChannelResponse,
    ChannelResponsePart,
    DeliveryResult,
    ResponsePartKind,
)


PLATFORM_CAPABILITIES: dict[ChannelPlatform, ChannelCapabilitySet] = {
    ChannelPlatform.CORE_API: ChannelCapabilitySet(text=True),
}


def capabilities_for(platform: ChannelPlatform | str) -> ChannelCapabilitySet:
    return PLATFORM_CAPABILITIES[ChannelPlatform(platform)]


def evaluate_delivery(
    response: ChannelResponse,
    capabilities: ChannelCapabilitySet,
) -> DeliveryResult:
    delivered: list[ChannelResponsePart] = []
    omitted: list[ChannelResponsePart] = []
    for part in response.parts:
        if _supports(part.kind, capabilities):
            delivered.append(part)
        else:
            omitted.append(part)

    if omitted and delivered:
        status = "degraded"
    elif omitted:
        status = "unsupported"
    else:
        status = "delivered"
    reason = "platform_capability_missing" if omitted else None
    return DeliveryResult(
        status=status,
        delivered_parts=tuple(delivered),
        omitted_parts=tuple(omitted),
        reason=reason,
    )


def _supports(kind: ResponsePartKind | str, capabilities: ChannelCapabilitySet) -> bool:
    capability_name = {
        ResponsePartKind.TEXT: "text",
        ResponsePartKind.IMAGE: "image",
        ResponsePartKind.FILE: "file",
        ResponsePartKind.AUDIO_ATTACHMENT: "audio_attachment",
        ResponsePartKind.NATIVE_VOICE: "native_voice",
        ResponsePartKind.TYPING: "typing",
        ResponsePartKind.RECALL: "recall",
    }[ResponsePartKind(kind)]
    return bool(getattr(capabilities, capability_name))
