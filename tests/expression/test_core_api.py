import asyncio

import pytest

from app.expression import (
    DeliveryHints,
    ResponseBundle,
    VoicePlan,
    VoiceStatus,
    normalize_core_api_text,
    plan_core_api_text,
    render_core_api_text,
    stream_core_api_text,
)


def test_core_api_text_round_trip_preserves_content() -> None:
    text = "收到，先从小步来。"

    bundle = plan_core_api_text(text)

    assert bundle.display_text == text
    assert normalize_core_api_text(text) == text
    assert bundle.voice.status is VoiceStatus.NOT_REQUESTED
    assert not bundle.sticker.should_send
    assert bundle.fallbacks == ()


def test_core_api_renderer_rejects_non_text_delivery() -> None:
    with pytest.raises(ValueError, match="absolute output_path"):
        ResponseBundle(
            display_text="不会重复发送",
            voice=VoicePlan(status=VoiceStatus.READY),
            delivery=DeliveryHints(suppress_display_text=True),
        )


def test_bundle_rejects_suppressed_text_without_ready_voice() -> None:
    with pytest.raises(ValueError, match="only be suppressed"):
        ResponseBundle(
            display_text="不能静默丢失",
            delivery=DeliveryHints(suppress_display_text=True),
        )


def test_core_api_stream_preserves_chunk_boundaries_and_whitespace() -> None:
    async def chunks():
        for chunk in ("收到，", " ", "先从小步来。"):
            yield chunk

    async def collect() -> list[str]:
        return [chunk async for chunk in stream_core_api_text(chunks())]

    assert asyncio.run(collect()) == ["收到，", " ", "先从小步来。"]
