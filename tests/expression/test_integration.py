from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.channels import capabilities_for
from app.channels.contracts import (
    ChannelCapabilitySet,
    ChannelEvent,
    ChannelEventType,
    ChannelIdentity,
    ChannelMessage,
    ChannelPlatform,
    ChannelThread,
    ChannelThreadType,
    ResponsePartKind,
)
from app.expression import (
    DeliveryContext,
    ExpressionPlanner,
    ExpressionRequest,
    capabilities_from_channel,
    delivery_context_from_event,
    provider_supports_tts,
    response_bundle_to_channel_response,
    with_provider_capability,
)
from app.providers.contracts import ProviderCapability, ProviderHealth, ProviderId
from app.providers.fakes import FakeProvider


def channel_event(thread_type: ChannelThreadType) -> ChannelEvent:
    timestamp = datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)
    return ChannelEvent(
        event_type=ChannelEventType.MESSAGE,
        platform=ChannelPlatform.CORE_API,
        identity=ChannelIdentity(platform=ChannelPlatform.CORE_API, user_id="10001"),
        thread=ChannelThread(
            platform=ChannelPlatform.CORE_API,
            thread_type=thread_type,
            thread_id="20001",
            group_id="20001" if thread_type is ChannelThreadType.GROUP else None,
        ),
        occurred_at=timestamp,
        message=ChannelMessage(message_id="30001", timestamp=timestamp, text="在吗"),
    )


def pending_voice_request() -> ExpressionRequest:
    return ExpressionRequest(
        display_text="我在。",
        voice_requested=True,
        voice_segments=("我在。",),
        provider_voice_capable=True,
    )


def _voice_file(root: Path) -> Path:
    path = (root / "voice.wav").resolve()
    path.write_bytes(b"RIFF-test")
    return path


def test_channel_capabilities_expose_only_core_api_runtime_contract() -> None:
    core_api = capabilities_from_channel(capabilities_for(ChannelPlatform.CORE_API))

    assert not core_api.voice
    assert not core_api.stickers
    assert not core_api.attachments


def test_channel_event_maps_group_context_but_not_owner_policy() -> None:
    context = delivery_context_from_event(
        channel_event(ChannelThreadType.GROUP),
        is_owner=True,
    )

    assert context == DeliveryContext(is_owner=True, is_group=True)


@pytest.mark.parametrize(
    ("capabilities", "health", "expected"),
    [
        (frozenset({ProviderCapability.TTS}), ProviderHealth.HEALTHY, True),
        (frozenset({ProviderCapability.TTS}), ProviderHealth.DEGRADED, True),
        (frozenset({ProviderCapability.TTS}), ProviderHealth.UNAVAILABLE, False),
        (frozenset({ProviderCapability.TTS}), ProviderHealth.CIRCUIT_OPEN, False),
        (frozenset({ProviderCapability.TEXT}), ProviderHealth.HEALTHY, False),
    ],
)
def test_provider_tts_capability_and_health_are_both_required(
    capabilities: frozenset[ProviderCapability],
    health: ProviderHealth,
    expected: bool,
) -> None:
    provider = FakeProvider(ProviderId("fake"), capabilities)

    assert provider_supports_tts(provider, health) is expected
    request = with_provider_capability(
        ExpressionRequest(display_text="text"),
        provider,
        health,
    )
    assert request.provider_voice_capable is expected


@pytest.mark.parametrize(
    ("channel_capabilities", "expected_kind"),
    [
        (ChannelCapabilitySet(native_voice=True), ResponsePartKind.NATIVE_VOICE),
        (ChannelCapabilitySet(audio_attachment=True), ResponsePartKind.AUDIO_ATTACHMENT),
    ],
)
def test_ready_voice_maps_to_generic_output_capability_without_duplicate_text(
    tmp_path: Path,
    channel_capabilities: ChannelCapabilitySet,
    expected_kind: ResponsePartKind,
) -> None:
    planner = ExpressionPlanner()
    bundle = planner.plan(
        pending_voice_request(),
        context=DeliveryContext(),
        capabilities=capabilities_from_channel(channel_capabilities),
    )
    finalized = planner.finalize_voice(
        bundle,
        output_path=_voice_file(tmp_path),
        controlled_media_root=tmp_path.resolve(),
    )

    response = response_bundle_to_channel_response(finalized, channel_capabilities)

    assert len(response.parts) == 1
    assert response.parts[0].kind == expected_kind
    assert all(part.kind != ResponsePartKind.TEXT for part in response.parts)


def test_failed_voice_plan_maps_back_to_text() -> None:
    capabilities = capabilities_for(ChannelPlatform.CORE_API)
    bundle = ExpressionPlanner().plan(
        pending_voice_request(),
        context=DeliveryContext(),
        capabilities=capabilities_from_channel(capabilities),
    )

    response = response_bundle_to_channel_response(
        bundle,
        capabilities,
        reply_to_message_id="30001",
    )

    assert [part.kind for part in response.parts] == [ResponsePartKind.TEXT]
    assert response.reply_to_message_id == "30001"


def test_response_conversion_rejects_capability_mismatch(tmp_path: Path) -> None:
    planner = ExpressionPlanner()
    voice_capabilities = ChannelCapabilitySet(native_voice=True)
    bundle = planner.plan(
        pending_voice_request(),
        context=DeliveryContext(),
        capabilities=capabilities_from_channel(voice_capabilities),
    )
    finalized = planner.finalize_voice(
        bundle,
        output_path=_voice_file(tmp_path),
        controlled_media_root=tmp_path.resolve(),
    )

    with pytest.raises(ValueError, match="voice-capable"):
        response_bundle_to_channel_response(finalized, ChannelCapabilitySet())
