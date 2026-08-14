"""Platform-neutral response expression planning."""

from .core_api import (
    normalize_core_api_text,
    plan_core_api_text,
    render_core_api_text,
    stream_core_api_text,
)
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
from .integration import (
    capabilities_from_channel,
    delivery_context_from_event,
    provider_supports_tts,
    response_bundle_to_channel_response,
    with_provider_capability,
)
from .planner import ExpressionPlanner, ExpressionRequest, request_from_dialogue_decisions

__all__ = [
    "DeliveryContext",
    "DeliveryFallback",
    "DeliveryHints",
    "ExpressionPlanner",
    "ExpressionRequest",
    "FallbackReason",
    "PlatformCapabilities",
    "ResponseBundle",
    "StickerPlan",
    "VoicePlan",
    "VoiceStatus",
    "capabilities_from_channel",
    "delivery_context_from_event",
    "provider_supports_tts",
    "request_from_dialogue_decisions",
    "response_bundle_to_channel_response",
    "with_provider_capability",
    "normalize_core_api_text",
    "plan_core_api_text",
    "render_core_api_text",
    "stream_core_api_text",
]
