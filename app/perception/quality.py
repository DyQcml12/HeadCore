from __future__ import annotations

import re

from app.perception.contracts import MemoryEligibility, PerceptionQuality


LOW_CONFIDENCE = 0.6


def clamp_confidence(value: object) -> float:
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def assess_memory(
    *, quality: PerceptionQuality | str, confidence: float, has_content: bool
) -> MemoryEligibility:
    if not has_content or quality == "failed":
        return MemoryEligibility(decision="deny", reasons=("no_reliable_content",))
    if quality == "conflicted":
        return MemoryEligibility(decision="review", reasons=("provider_conflict",))
    if confidence < LOW_CONFIDENCE:
        return MemoryEligibility(decision="review", reasons=("low_confidence",))
    if quality in {"degraded", PerceptionQuality.UNCERTAIN}:
        return MemoryEligibility(decision="review", reasons=("degraded_quality",))
    return MemoryEligibility(decision="allow")


def text_agreement(left: str, right: str) -> bool:
    left_norm = _normalize(left)
    right_norm = _normalize(right)
    if not left_norm or not right_norm:
        return True
    return left_norm in right_norm or right_norm in left_norm


def _normalize(text: str) -> str:
    return re.sub(r"\W+", "", text, flags=re.UNICODE).lower()
