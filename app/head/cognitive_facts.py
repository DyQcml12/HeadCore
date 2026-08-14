from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, replace
from typing import Iterable

from app.head.contracts import (
    CognitiveFact,
    CognitiveFactKind,
    CognitiveFactSourceKind,
    CognitiveFactStatus,
)
from app.head.world_model import belief_strength
from app.storage.chat_repository import ChatRepository


FACT_MEMORY_TYPE = "head_world_fact"
FACT_REVOKE_MEMORY_TYPE = "head_world_fact_revoke"
MAX_FACTS_PER_USER = 64


def encode_cognitive_fact(fact: CognitiveFact) -> str:
    fact = _normalize_fact(fact)
    _validate_fact(fact)
    payload = asdict(fact)
    payload["status"] = fact.status.value
    payload["kind"] = fact.kind.value
    payload["source_kind"] = fact.source_kind.value
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_cognitive_fact(content: str) -> CognitiveFact:
    try:
        payload = json.loads(content)
        source_id = str(payload["source_id"])
        fact = CognitiveFact(
            fact_id=str(payload["fact_id"]),
            key=str(payload["key"]),
            value=str(payload["value"]),
            source_id=source_id,
            observed_at=str(payload["observed_at"]),
            expires_at=str(payload["expires_at"]),
            confidence=float(payload["confidence"]),
            version=int(payload.get("version", 1)),
            status=CognitiveFactStatus(str(payload.get("status", "active"))),
            kind=CognitiveFactKind(str(payload.get("kind", "observation"))),
            source_kind=CognitiveFactSourceKind(
                str(payload.get("source_kind", "world_evidence"))
            ),
            supporting_source_ids=tuple(
                str(item) for item in payload.get("supporting_source_ids", (source_id,))
            ),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cognitive fact") from exc
    fact = _normalize_fact(fact)
    _validate_fact(fact)
    return fact


async def save_cognitive_fact(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str | None,
    fact: CognitiveFact,
    allow_write: bool,
) -> None:
    if not allow_write:
        return
    await repository.save_memory(
        user_id=user_id,
        session_id=session_id,
        memory_type=FACT_MEMORY_TYPE,
        content=encode_cognitive_fact(fact),
        source_message_id=source_message_id,
        confidence=fact.confidence,
    )


async def revoke_cognitive_fact(
    repository: ChatRepository,
    *,
    user_id: str,
    session_id: str,
    source_message_id: str | None,
    fact_id: str,
    allow_write: bool,
) -> None:
    if not allow_write:
        return
    normalized = fact_id.strip()
    if not normalized:
        raise ValueError("fact_id is required")
    await repository.save_memory(
        user_id=user_id,
        session_id=session_id,
        memory_type=FACT_REVOKE_MEMORY_TYPE,
        content=json.dumps({"fact_id": normalized}, separators=(",", ":")),
        source_message_id=source_message_id,
        confidence=1.0,
    )


async def load_cognitive_facts(
    repository: ChatRepository,
    *,
    user_id: str,
    now: dt.datetime | None = None,
) -> tuple[CognitiveFact, ...]:
    records = await repository.list_memories(
        user_id=user_id,
        memory_types=[FACT_MEMORY_TYPE, FACT_REVOKE_MEMORY_TYPE],
        limit=MAX_FACTS_PER_USER * 2,
    )
    revoked: set[str] = set()
    facts: dict[str, CognitiveFact] = {}
    for record in records:
        if record.memory_type == FACT_REVOKE_MEMORY_TYPE:
            try:
                revoked.add(str(json.loads(record.content)["fact_id"]))
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            continue
        try:
            fact = decode_cognitive_fact(record.content)
        except ValueError:
            continue
        current = facts.get(fact.fact_id)
        if current is None or fact.version >= current.version:
            facts[fact.fact_id] = fact
    return resolve_cognitive_facts(facts.values(), revoked_fact_ids=revoked, now=now)


def resolve_cognitive_facts(
    facts: Iterable[CognitiveFact],
    *,
    revoked_fact_ids: set[str] | None = None,
    now: dt.datetime | None = None,
) -> tuple[CognitiveFact, ...]:
    current_time = _aware(now or dt.datetime.now(dt.UTC))
    revoked = revoked_fact_ids or set()
    resolved: list[CognitiveFact] = []
    for raw_fact in facts:
        fact = _normalize_fact(raw_fact)
        _validate_fact(fact)
        if fact.fact_id in revoked:
            resolved.append(replace(fact, status=CognitiveFactStatus.REVOKED))
        else:
            resolved.append(replace(fact, status=CognitiveFactStatus.ACTIVE))

    # A higher version can replace an older fact only when it does not lower
    # confidence. A lower-confidence value change remains active beside the old
    # value so ordinary conflict handling forces later confirmation.
    version_resolved: list[CognitiveFact] = []
    for fact in resolved:
        if fact.status == CognitiveFactStatus.REVOKED:
            version_resolved.append(fact)
            continue

        newer = [
            candidate
            for candidate in resolved
            if candidate.status != CognitiveFactStatus.REVOKED
            and candidate.key == fact.key
            and candidate.version > fact.version
            and _can_supersede(fact, candidate)
        ]
        if newer:
            latest_version = max(candidate.version for candidate in newer)
            newest = [
                candidate
                for candidate in newer
                if candidate.version == latest_version
            ]
            newer_values = {candidate.value for candidate in newest}
            newer_confidence = max(
                (candidate.confidence for candidate in newest), default=-1.0
            )
            if fact.value in newer_values or newer_confidence >= fact.confidence:
                version_resolved.append(replace(fact, status=CognitiveFactStatus.SUPERSEDED))
            elif _parse_time(fact.expires_at) <= current_time:
                version_resolved.append(replace(fact, status=CognitiveFactStatus.STALE))
            else:
                version_resolved.append(fact)
        elif _parse_time(fact.expires_at) <= current_time:
            version_resolved.append(replace(fact, status=CognitiveFactStatus.STALE))
        else:
            version_resolved.append(fact)

    reinforced = _reinforce_matching_world_evidence(version_resolved)

    active_values: dict[str, set[str]] = {}
    for fact in reinforced:
        if fact.status == CognitiveFactStatus.ACTIVE:
            if fact.kind == CognitiveFactKind.HYPOTHESIS:
                continue
            active_values.setdefault(fact.key, set()).add(fact.value)
    conflicted_keys = {key for key, values in active_values.items() if len(values) > 1}
    return tuple(
        replace(fact, status=CognitiveFactStatus.CONFLICTED)
        if fact.status == CognitiveFactStatus.ACTIVE and fact.key in conflicted_keys
        else fact
        for fact in sorted(reinforced, key=lambda item: (item.key, item.fact_id))
    )


def cognitive_fact_strength(
    fact: CognitiveFact,
    *,
    now: dt.datetime | None = None,
) -> float:
    """Recency-decayed belief strength for an active fact.

    Expired or non-active facts carry zero strength; the projection layer uses
    this value for ordering so fresh evidence outranks old evidence.
    """
    current_time = _aware(now or dt.datetime.now(dt.UTC))
    if fact.status != CognitiveFactStatus.ACTIVE:
        return 0.0
    if _parse_time(fact.expires_at) <= current_time:
        return 0.0
    return belief_strength(
        fact.confidence,
        since_at=_parse_time(fact.observed_at),
        now=current_time,
    )


def project_cognitive_facts(
    facts: Iterable[CognitiveFact],
    *,
    limit: int = 8,
    now: dt.datetime | None = None,
) -> tuple[str, ...]:
    current_time = _aware(now or dt.datetime.now(dt.UTC))
    active: dict[tuple[str, str], CognitiveFact] = {}
    for raw_fact in facts:
        fact = _normalize_fact(raw_fact)
        if fact.status != CognitiveFactStatus.ACTIVE or not _is_confirmed_world_fact(fact):
            continue
        identity = (fact.key, fact.value)
        current = active.get(identity)
        if current is None or fact.confidence > current.confidence:
            active[identity] = fact
    projected = sorted(
        active.values(),
        key=lambda fact: (
            -cognitive_fact_strength(fact, now=current_time),
            fact.key,
            fact.fact_id,
        ),
    )
    return tuple(
        f"世界事实[{fact.key}]={fact.value};source={fact.source_id};"
        f"sources={','.join(fact.supporting_source_ids)};expires={fact.expires_at}"
        for fact in projected[:limit]
    )


def project_cognitive_fact_uncertainties(
    facts: Iterable[CognitiveFact], *, limit: int = 8
) -> tuple[str, ...]:
    """Expose fact health to HeadState without projecting the fact value itself."""
    values: list[str] = []
    for fact in sorted(facts, key=lambda item: (item.key, item.fact_id)):
        if fact.status == CognitiveFactStatus.CONFLICTED:
            values.append(f"cognitive_fact_conflict:{fact.key}")
        elif fact.status == CognitiveFactStatus.STALE:
            values.append(f"cognitive_fact_stale:{fact.key}")
        elif (
            fact.status == CognitiveFactStatus.ACTIVE
            and fact.kind == CognitiveFactKind.HYPOTHESIS
        ):
            values.append(f"cognitive_fact_hypothesis:{fact.key}")
        elif (
            fact.status == CognitiveFactStatus.ACTIVE
            and fact.source_kind == CognitiveFactSourceKind.USER_REPORT
        ):
            values.append(f"cognitive_fact_unverified_user_report:{fact.key}")
    return tuple(dict.fromkeys(values))[:limit]


def _reinforce_matching_world_evidence(
    facts: Iterable[CognitiveFact],
) -> list[CognitiveFact]:
    groups: dict[tuple[str, str], list[CognitiveFact]] = {}
    values = list(facts)
    for fact in values:
        if fact.status == CognitiveFactStatus.ACTIVE and _is_confirmed_world_fact(fact):
            groups.setdefault((fact.key, fact.value), []).append(fact)

    reinforced: dict[str, CognitiveFact] = {}
    for group in groups.values():
        confidence_by_source: dict[str, float] = {}
        source_ids: set[str] = set()
        for fact in group:
            source_ids.update(fact.supporting_source_ids)
            confidence_by_source[fact.source_id] = max(
                confidence_by_source.get(fact.source_id, 0.0), fact.confidence
            )
        if len(confidence_by_source) < 2:
            continue
        remaining_uncertainty = 1.0
        for confidence in confidence_by_source.values():
            remaining_uncertainty *= 1.0 - confidence
        reinforced_confidence = 1.0 - remaining_uncertainty
        provenance = tuple(sorted(source_ids))
        for fact in group:
            reinforced[fact.fact_id] = replace(
                fact,
                kind=CognitiveFactKind.BELIEF,
                confidence=reinforced_confidence,
                supporting_source_ids=provenance,
            )
    return [reinforced.get(fact.fact_id, fact) for fact in values]


def _can_supersede(old: CognitiveFact, new: CognitiveFact) -> bool:
    if _is_confirmed_world_fact(old):
        return _is_confirmed_world_fact(new)
    return old.kind == new.kind and old.source_kind == new.source_kind


def _is_confirmed_world_fact(fact: CognitiveFact) -> bool:
    return (
        fact.source_kind == CognitiveFactSourceKind.WORLD_EVIDENCE
        and fact.kind in {CognitiveFactKind.OBSERVATION, CognitiveFactKind.BELIEF}
    )


def _normalize_fact(fact: CognitiveFact) -> CognitiveFact:
    source_ids = tuple(sorted({fact.source_id, *fact.supporting_source_ids}))
    return replace(
        fact,
        kind=CognitiveFactKind(fact.kind),
        source_kind=CognitiveFactSourceKind(fact.source_kind),
        supporting_source_ids=source_ids,
    )


def _validate_fact(fact: CognitiveFact) -> None:
    if not all(value.strip() for value in (fact.fact_id, fact.key, fact.value, fact.source_id)):
        raise ValueError("cognitive fact identifiers and value must be non-empty")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,95}", fact.key):
        raise ValueError("cognitive fact key must use a bounded dotted identifier")
    if any(character in fact.value for character in "\r\n\x00") or len(fact.value) > 240:
        raise ValueError("cognitive fact value must be a single line of at most 240 characters")
    if len(fact.fact_id) > 96:
        raise ValueError("cognitive fact identifiers must be at most 96 characters")
    source_ids = (fact.source_id, *fact.supporting_source_ids)
    if not fact.supporting_source_ids or any(
        not source_id.strip()
        or len(source_id) > 96
        or any(character.isspace() or ord(character) < 32 for character in source_id)
        for source_id in source_ids
    ):
        raise ValueError(
            "cognitive fact source identifiers must be non-empty bounded single tokens"
        )
    if not 0.0 <= fact.confidence <= 1.0:
        raise ValueError("cognitive fact confidence must be between 0 and 1")
    if fact.version < 1:
        raise ValueError("cognitive fact version must be positive")
    observed = _parse_time(fact.observed_at)
    expires = _parse_time(fact.expires_at)
    if expires <= observed:
        raise ValueError("cognitive fact must expire after it was observed")


def _parse_time(value: str) -> dt.datetime:
    try:
        return _aware(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError("cognitive fact timestamp must be ISO-8601") from exc


def _aware(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise ValueError("cognitive fact timestamps must include a timezone")
    return value.astimezone(dt.UTC)
