from dataclasses import fields
from pathlib import Path

import pytest

from app.dialogue.types import StickerDecision, VoiceDecision
from app.expression import (
    DeliveryContext,
    ExpressionPlanner,
    ExpressionRequest,
    FallbackReason,
    PlatformCapabilities,
    ResponseBundle,
    VoiceStatus,
    request_from_dialogue_decisions,
)


def reasons(bundle: ResponseBundle) -> set[FallbackReason]:
    return {fallback.reason for fallback in bundle.fallbacks}


def voice_request(**overrides: object) -> ExpressionRequest:
    values: dict[str, object] = {
        "display_text": "我在，慢慢说。",
        "voice_requested": True,
        "voice_segments": ("我在，", "慢慢说。"),
        "voice_owner_only": True,
        "provider_voice_capable": True,
    }
    values.update(overrides)
    return ExpressionRequest(**values)


def voice_capabilities(**overrides: object) -> PlatformCapabilities:
    values: dict[str, object] = {"voice": True, "voice_in_group": True}
    values.update(overrides)
    return PlatformCapabilities(**values)


def test_contract_has_no_platform_private_types() -> None:
    annotations = {item.name: str(item.type) for item in fields(ResponseBundle)}

    assert "nonebot" not in str(annotations).lower()
    assert "onebot" not in str(annotations).lower()
    assert "hermes" not in str(annotations).lower()


def test_owner_only_voice_falls_back_for_non_owner() -> None:
    bundle = ExpressionPlanner().plan(
        voice_request(),
        context=DeliveryContext(is_owner=False),
        capabilities=voice_capabilities(),
    )

    assert bundle.voice.status is VoiceStatus.FALLBACK_TO_TEXT
    assert FallbackReason.VOICE_OWNER_REQUIRED in reasons(bundle)
    assert not bundle.delivery.suppress_display_text


def test_group_voice_falls_back_when_platform_disallows_it() -> None:
    bundle = ExpressionPlanner().plan(
        voice_request(),
        context=DeliveryContext(is_owner=True, is_group=True),
        capabilities=voice_capabilities(voice_in_group=False),
    )

    assert FallbackReason.VOICE_GROUP_UNSUPPORTED in reasons(bundle)
    assert bundle.voice.status is VoiceStatus.FALLBACK_TO_TEXT


@pytest.mark.parametrize(
    ("capabilities", "provider_capable", "reason"),
    [
        (voice_capabilities(voice=False), True, FallbackReason.VOICE_CAPABILITY_UNSUPPORTED),
        (voice_capabilities(), False, FallbackReason.VOICE_PROVIDER_UNAVAILABLE),
    ],
)
def test_voice_capability_fallbacks_have_reason_codes(
    capabilities: PlatformCapabilities,
    provider_capable: bool,
    reason: FallbackReason,
) -> None:
    bundle = ExpressionPlanner().plan(
        voice_request(provider_voice_capable=provider_capable),
        context=DeliveryContext(is_owner=True),
        capabilities=capabilities,
    )

    assert reason in reasons(bundle)


def test_voice_platform_segment_limit_falls_back_to_text() -> None:
    bundle = ExpressionPlanner().plan(
        voice_request(),
        context=DeliveryContext(is_owner=True),
        capabilities=voice_capabilities(max_voice_segments=1),
    )

    assert FallbackReason.PLATFORM_LIMIT in reasons(bundle)
    assert bundle.voice.status is VoiceStatus.FALLBACK_TO_TEXT


def test_tts_success_suppresses_duplicate_text(tmp_path: Path) -> None:
    planner = ExpressionPlanner()
    bundle = planner.plan(
        voice_request(),
        context=DeliveryContext(is_owner=True),
        capabilities=voice_capabilities(),
    )
    output_path = (tmp_path / "voice.wav").resolve()
    output_path.write_bytes(b"RIFF-test")

    finalized = planner.finalize_voice(
        bundle,
        output_path=output_path,
        controlled_media_root=tmp_path.resolve(),
    )

    assert finalized.voice.status is VoiceStatus.READY
    assert finalized.voice.output_path == output_path
    assert finalized.delivery.suppress_display_text


def test_tts_failure_restores_text_delivery(tmp_path: Path) -> None:
    planner = ExpressionPlanner()
    bundle = planner.plan(
        voice_request(),
        context=DeliveryContext(is_owner=True),
        capabilities=voice_capabilities(),
    )

    finalized = planner.finalize_voice(
        bundle,
        output_path=None,
        controlled_media_root=tmp_path.resolve(),
        error_detail="synthesis_failed",
    )

    assert finalized.voice.status is VoiceStatus.FALLBACK_TO_TEXT
    assert FallbackReason.VOICE_TTS_FAILED in reasons(finalized)
    assert not finalized.delivery.suppress_display_text


def test_tts_failure_detail_only_keeps_safe_reason_code(tmp_path: Path) -> None:
    planner = ExpressionPlanner()
    bundle = planner.plan(
        voice_request(),
        context=DeliveryContext(is_owner=True),
        capabilities=voice_capabilities(),
    )

    finalized = planner.finalize_voice(
        bundle,
        output_path=None,
        controlled_media_root=tmp_path.resolve(),
        error_detail="request failed with token secret-value",
    )

    assert finalized.fallbacks[-1].detail is None


def test_voice_output_must_be_absolute_and_controlled(tmp_path: Path) -> None:
    planner = ExpressionPlanner()
    bundle = planner.plan(
        voice_request(),
        context=DeliveryContext(is_owner=True),
        capabilities=voice_capabilities(),
    )

    relative = planner.finalize_voice(
        bundle,
        output_path=Path("voice.wav"),
        controlled_media_root=tmp_path.resolve(),
    )
    escaped = planner.finalize_voice(
        bundle,
        output_path=tmp_path.parent / "voice.wav",
        controlled_media_root=tmp_path.resolve(),
    )

    assert FallbackReason.MEDIA_PATH_INVALID in reasons(relative)
    assert FallbackReason.MEDIA_PATH_INVALID in reasons(escaped)


def test_sticker_cooldown_and_platform_capability_are_explicit() -> None:
    planner = ExpressionPlanner()
    request = ExpressionRequest(
        display_text="好耶！",
        sticker_requested=True,
        sticker_asset_id="happy-1",
        sticker_intent="celebrate",
        sticker_cooldown_allowed=False,
    )
    cooldown = planner.plan(
        request,
        context=DeliveryContext(),
        capabilities=PlatformCapabilities(stickers=True),
    )
    unsupported = planner.plan(
        ExpressionRequest(
            display_text="好耶！",
            sticker_requested=True,
            sticker_asset_id="happy-1",
            sticker_intent="celebrate",
        ),
        context=DeliveryContext(),
        capabilities=PlatformCapabilities(stickers=False),
    )

    assert not cooldown.sticker.should_send
    assert FallbackReason.STICKER_COOLDOWN in reasons(cooldown)
    assert FallbackReason.STICKER_CAPABILITY_UNSUPPORTED in reasons(unsupported)


def test_missing_sticker_asset_has_explicit_fallback() -> None:
    bundle = ExpressionPlanner().plan(
        ExpressionRequest(display_text="好耶！", sticker_requested=True),
        context=DeliveryContext(),
        capabilities=PlatformCapabilities(stickers=True),
    )

    assert not bundle.sticker.should_send
    assert FallbackReason.STICKER_ASSET_MISSING in reasons(bundle)


def test_unsupported_or_uncontrolled_attachment_is_removed(tmp_path: Path) -> None:
    path = (tmp_path / "reply.bin").resolve()
    request = ExpressionRequest(display_text="文件见附件。", attachment_paths=(path,))
    planner = ExpressionPlanner()

    unsupported = planner.plan(
        request,
        context=DeliveryContext(),
        capabilities=PlatformCapabilities(attachments=False),
        controlled_media_root=tmp_path.resolve(),
    )
    uncontrolled = planner.plan(
        request,
        context=DeliveryContext(),
        capabilities=PlatformCapabilities(attachments=True),
        controlled_media_root=(tmp_path / "other").resolve(),
    )

    assert unsupported.delivery.attachment_paths == ()
    assert FallbackReason.ATTACHMENT_CAPABILITY_UNSUPPORTED in reasons(unsupported)
    assert uncontrolled.delivery.attachment_paths == ()
    assert FallbackReason.MEDIA_PATH_INVALID in reasons(uncontrolled)


def test_existing_dialogue_decisions_map_to_expression_request() -> None:
    request = request_from_dialogue_decisions(
        display_text="好耶！",
        voice=VoiceDecision(True, "playful", 0.8, ["emotion:happy"]),
        sticker=StickerDecision(True, "celebrate", "happy", 0.8, ["intent:celebrate"]),
        sticker_asset_id="happy-1",
        provider_voice_capable=True,
        voice_owner_only=True,
    )

    assert request.voice_segments == ("好耶！",)
    assert request.sticker_intent == "celebrate"
    assert request.sticker_asset_id == "happy-1"
    assert request.voice_owner_only


def test_invalid_requests_and_capabilities_fail_early() -> None:
    with pytest.raises(ValueError, match="display_text"):
        ExpressionRequest(display_text=" ")
    with pytest.raises(ValueError, match="voice_segments"):
        ExpressionRequest(display_text="text", voice_requested=True)
    with pytest.raises(ValueError, match="max_voice_segments"):
        PlatformCapabilities(max_voice_segments=0)
    with pytest.raises(ValueError, match="voice_format"):
        ExpressionRequest(display_text="text", voice_format="../../html")

    normalized = ExpressionRequest(display_text="text", voice_format=" WAV ")
    assert normalized.voice_format == "wav"
