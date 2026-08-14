from __future__ import annotations

from pathlib import Path

from app.channels.contracts import AttachmentKind, ChannelAttachment, ChannelEvent
from app.perception.contracts import (
    PerceptionInput,
    PerceptionObservation,
    PerceptionQuality,
    ProviderTrace,
)
from app.perception.memory import evaluate_memory_eligibility
from app.perception.normalization import redact_text
from app.providers.contracts import ProviderTrace as RoutingProviderTrace
from app.providers.contracts import AsrResult
from app.audio.quality import evaluate_asr_text_quality


_MODALITY_BY_ATTACHMENT = {
    AttachmentKind.AUDIO: "audio",
    AttachmentKind.IMAGE: "image",
    AttachmentKind.FILE: "file",
}


def perception_input_from_channel_event(
    event: ChannelEvent,
    *,
    attachment_kind: AttachmentKind | str,
    local_path: Path | None = None,
    remote_url: str | None = None,
    mime_type: str | None = None,
) -> PerceptionInput:
    if event.message is None:
        raise ValueError("channel event does not contain a message")
    kind = AttachmentKind(attachment_kind)
    modality = _MODALITY_BY_ATTACHMENT.get(kind)
    if modality is None:
        raise ValueError(f"attachment kind {kind.value} is not perceptible")
    attachment = next(
        (item for item in event.message.attachments if item.kind == kind),
        None,
    )
    if attachment is None:
        raise ValueError(f"channel event does not contain a {kind.value} attachment")
    return _build_input(
        event,
        attachment,
        modality=modality,
        local_path=local_path,
        remote_url=remote_url,
        mime_type=mime_type,
    )


def routing_trace_to_perception(trace: RoutingProviderTrace) -> tuple[ProviderTrace, ...]:
    first_provider = trace.attempts[0].provider_id if trace.attempts else None
    return tuple(
        ProviderTrace(
            provider=str(attempt.provider_id),
            latency_ms=round(attempt.duration_seconds * 1000, 2),
            fallback=first_provider is not None and attempt.provider_id != first_provider,
            success=attempt.success,
            error_code=attempt.error_code.value if attempt.error_code else None,
        )
        for attempt in trace.attempts
    )


def _build_input(
    event: ChannelEvent,
    attachment: ChannelAttachment,
    *,
    modality: str,
    local_path: Path | None,
    remote_url: str | None,
    mime_type: str | None,
) -> PerceptionInput:
    return PerceptionInput(
        modality=modality,  # type: ignore[arg-type]
        source=str(event.platform),
        local_path=local_path,
        remote_url=remote_url,
        declared_mime=mime_type or attachment.media_type,
        declared_size_bytes=attachment.size_bytes,
    )


def normalize_asr_result(
    raw: AsrResult,
    value: PerceptionInput,
    *,
    traces: tuple[ProviderTrace, ...],
) -> PerceptionObservation:
    text = redact_text(raw.text)
    report = evaluate_asr_text_quality(text)
    confidence = raw.confidence if raw.confidence is not None else report.score
    confidence = max(0.0, min(1.0, confidence))
    quality = PerceptionQuality.GOOD if report.passed and confidence >= 0.8 else PerceptionQuality.UNCERTAIN
    reasons = tuple(report.reasons)
    memory = evaluate_memory_eligibility(
        confidence=confidence,
        quality=quality,
        has_text=bool(text),
    )
    return PerceptionObservation(
        modality=value.modality,
        text=text,
        emotion=raw.emotion,
        language=raw.language,
        confidence=confidence,
        quality=quality,
        quality_reasons=reasons,
        traces=traces,
        memory_eligibility=memory,
        metadata={
            "source": value.source,
            "emotion_source": raw.emotion_source,
            "emotion_confidence": raw.emotion_confidence,
        },
    )
