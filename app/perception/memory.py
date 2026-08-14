from __future__ import annotations

from app.perception.contracts import MemoryDecision, MemoryEligibility, PerceptionQuality


def evaluate_memory_eligibility(
    *, confidence: float, quality: PerceptionQuality | str, has_text: bool, conflict: bool = False
) -> MemoryEligibility:
    if quality == PerceptionQuality.FAILED or not has_text:
        return MemoryEligibility(decision=MemoryDecision.DENY, reasons=("no_reliable_observation",))
    if confidence < 0.5:
        return MemoryEligibility(decision=MemoryDecision.DENY, reasons=("low_confidence",))
    if conflict or quality == PerceptionQuality.UNCERTAIN or confidence < 0.8:
        reasons = ("provider_conflict",) if conflict else ("requires_review",)
        return MemoryEligibility(decision=MemoryDecision.REVIEW, reasons=reasons)
    return MemoryEligibility(decision=MemoryDecision.ALLOW)

