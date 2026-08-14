from datetime import datetime, timezone

import pytest

from app.channels.contracts import (
    AttachmentKind,
    ChannelAttachment,
    ChannelEvent,
    ChannelIdentity,
    ChannelMessage,
    ChannelThread,
)
from app.perception.integration import (
    perception_input_from_channel_event,
    routing_trace_to_perception,
)
from app.providers.contracts import (
    ProviderAttempt,
    ProviderCapability,
    ProviderErrorCode,
    ProviderId,
    ProviderTrace,
)


def _event() -> ChannelEvent:
    now = datetime.now(timezone.utc)
    return ChannelEvent(
        event_type="message",
        platform="qq",
        identity=ChannelIdentity(platform="qq", user_id="123"),
        thread=ChannelThread(platform="qq", thread_type="private", thread_id="123"),
        occurred_at=now,
        message=ChannelMessage(
            message_id="456",
            timestamp=now,
            attachments=(
                ChannelAttachment(
                    kind="image",
                    display_name="sample.png",
                    size_bytes=1024,
                    source_ref="onebot:file_id:opaque",
                    summary="QQ image attachment",
                ),
            ),
        ),
    )


def test_channel_attachment_requires_explicit_runtime_location() -> None:
    value = perception_input_from_channel_event(
        _event(),
        attachment_kind=AttachmentKind.IMAGE,
        remote_url="https://example.com/sample.png",
        mime_type="image/png",
    )

    assert value.modality == "image"
    assert value.source == "qq"
    assert value.remote_url == "https://example.com/sample.png"
    assert value.declared_size_bytes == 1024
    assert value.declared_mime == "image/png"


def test_non_perceptible_or_missing_attachment_is_rejected() -> None:
    with pytest.raises(ValueError, match="audio attachment"):
        perception_input_from_channel_event(_event(), attachment_kind=AttachmentKind.AUDIO)
    with pytest.raises(ValueError, match="not perceptible"):
        perception_input_from_channel_event(_event(), attachment_kind=AttachmentKind.VIDEO)


def test_s6_trace_maps_to_s3_trace_without_sensitive_details() -> None:
    trace = ProviderTrace(
        capability=ProviderCapability.ASR,
        attempts=(
            ProviderAttempt(
                provider_id=ProviderId("sensevoice"),
                capability=ProviderCapability.ASR,
                attempt=1,
                started_at=0.0,
                duration_seconds=0.2,
                success=False,
                error_code=ProviderErrorCode.MODEL_MISSING,
                details={"token": "must-not-cross-boundary"},
            ),
            ProviderAttempt(
                provider_id=ProviderId("funasr"),
                capability=ProviderCapability.ASR,
                attempt=1,
                started_at=0.2,
                duration_seconds=0.1,
                success=True,
            ),
        ),
    )

    mapped = routing_trace_to_perception(trace)

    assert mapped[0].error_code == "model_missing"
    assert mapped[0].latency_ms == 200.0
    assert mapped[1].fallback is True
    assert "must-not-cross-boundary" not in repr(mapped)



