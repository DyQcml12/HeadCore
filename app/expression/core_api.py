from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator

from app.channels import capabilities_for
from app.channels.contracts import ChannelPlatform, ResponsePartKind

from .integration import capabilities_from_channel, response_bundle_to_channel_response
from .models import DeliveryContext, ResponseBundle
from .planner import ExpressionPlanner, ExpressionRequest


def plan_core_api_text(text: str) -> ResponseBundle:
    channel_capabilities = capabilities_for(ChannelPlatform.CORE_API)
    return ExpressionPlanner().plan(
        ExpressionRequest(display_text=text),
        context=DeliveryContext(),
        capabilities=capabilities_from_channel(channel_capabilities),
    )


def render_core_api_text(bundle: ResponseBundle) -> str:
    response = response_bundle_to_channel_response(
        bundle,
        capabilities_for(ChannelPlatform.CORE_API),
    )
    text_parts = [part.content for part in response.parts if part.kind == ResponsePartKind.TEXT]
    if len(text_parts) != 1 or len(response.parts) != 1:
        raise ValueError("Core API expression bundle must resolve to exactly one text part")
    return text_parts[0]


def normalize_core_api_text(text: str) -> str:
    return render_core_api_text(plan_core_api_text(text))


async def stream_core_api_text(chunks: AsyncIterable[str]) -> AsyncIterator[str]:
    async for chunk in chunks:
        if chunk.strip():
            yield normalize_core_api_text(chunk)
        else:
            yield chunk

