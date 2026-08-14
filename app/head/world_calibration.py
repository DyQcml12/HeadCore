from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from app.head.contracts import CognitiveFact, CognitiveFactStatus


@dataclass(frozen=True)
class FactCalibrationReport:
    written_facts: tuple[CognitiveFact, ...]
    superseded_facts: tuple[CognitiveFact, ...]
    conflict_keys: tuple[str, ...]
    duplicate_count: int


def calibrate_facts_with_observations(
    existing: Iterable[CognitiveFact],
    incoming: Iterable[CognitiveFact],
) -> FactCalibrationReport:
    """Reconcile incoming world-evidence facts against the current fact set.

    Deterministic rules:
    - same key + same value -> duplicate, skip (no write);
    - same key + same source + different value with a higher version -> the old
      fact is marked SUPERSEDED and the new one is written;
    - same key + different source + different value -> both stay ACTIVE so the
      existing resolve_cognitive_facts conflict rule marks them CONFLICTED;
    - expired/STALE facts are left untouched and the new fact is written.
    No user content or source bodies enter this module."""
    active_by_key: dict[str, CognitiveFact] = {}
    for fact in existing:
        if fact.status != CognitiveFactStatus.ACTIVE:
            continue
        current = active_by_key.get(fact.key)
        if current is None or fact.version > current.version:
            active_by_key[fact.key] = fact
    written: list[CognitiveFact] = []
    superseded: list[CognitiveFact] = []
    conflict_keys: list[str] = []
    duplicate_count = 0
    for fact in incoming:
        current = active_by_key.get(fact.key)
        if current is None:
            written.append(fact)
            active_by_key[fact.key] = fact
            continue
        if current.value == fact.value:
            duplicate_count += 1
            continue
        if current.source_id == fact.source_id and fact.version > current.version:
            superseded.append(replace(current, status=CognitiveFactStatus.SUPERSEDED))
            active_by_key[fact.key] = fact
            written.append(fact)
            continue
        conflict_keys.append(fact.key)
        written.append(fact)
    return FactCalibrationReport(
        written_facts=tuple(written),
        superseded_facts=tuple(superseded),
        conflict_keys=tuple(dict.fromkeys(conflict_keys)),
        duplicate_count=duplicate_count,
    )
