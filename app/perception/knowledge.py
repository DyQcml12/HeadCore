from __future__ import annotations

from app.knowledge.intake import MemoryCandidateInput
from app.knowledge.models import MemoryScope
from app.perception.contracts import PerceptionObservation


_QUALITY_SCORE = {
    "good": 1.0,
    "uncertain": 0.7,
    "degraded": 0.4,
    "conflicted": 0.4,
    "failed": 0.0,
}


def observation_to_memory_candidate(
    observation: PerceptionObservation,
    *,
    profile_id: str,
    source_id: str,
    key: str,
    scope: MemoryScope = MemoryScope.PROFILE_PRIVATE,
    persona_id: str | None = None,
) -> MemoryCandidateInput:
    return MemoryCandidateInput(
        profile_id=profile_id,
        key=key,
        value=observation.text.strip(),
        scope=scope,
        source_type=f"perception:{observation.modality}",
        source_id=source_id,
        confidence=observation.confidence,
        eligibility=str(observation.memory_eligibility.decision),  # type: ignore[arg-type]
        eligibility_reasons=observation.memory_eligibility.reasons,
        persona_id=persona_id,
        observation_quality=_QUALITY_SCORE[str(observation.quality)],
    )
