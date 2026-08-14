from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.head.self_profile import SelfProfile, utc_now_iso
from app.head.self_profile_store import load_self_profile, save_self_profile
from app.storage.chat_repository import ChatRepository


SELF_REFLECTION_AUDIT_TYPE = "head_reflection_audit"
SELF_REFLECTION_SESSION_ID = "head-self-reflection"
MIN_FEEDBACK_EVIDENCE = 3
MAX_FIELD_CHANGES_PER_REFLECTION = 2
MAX_PROFILE_BOUNDARIES = 5

_CORRECTED_BOUNDARY = "被指出问题时先收住，再按用户要的方式答"
_ADVICE_REJECTED_BOUNDARY = "不主动给未经请求的建议"
_STOPPED_BOUNDARY = "察觉用户叫停就先停，不追问"


@dataclass(frozen=True)
class ReflectionSources:
    corrected: int
    advice_rejected: int
    stopped: int
    messages_since: int

    @property
    def feedback_total(self) -> int:
        return self.corrected + self.advice_rejected + self.stopped


async def collect_reflection_sources(
    repository: ChatRepository,
    *,
    user_id: str,
    since_at: str,
) -> ReflectionSources:
    """Aggregate deterministic, already-redacted feedback evidence only."""
    feedback_records = await repository.list_memories(
        user_id=user_id,
        memory_types=["head_feedback"],
        limit=50,
    )
    corrected = advice_rejected = stopped = 0
    for record in feedback_records:
        if since_at and record.created_at <= since_at:
            continue
        try:
            payload = json.loads(record.content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        outcome = payload.get("outcome")
        if outcome == "corrected":
            corrected += 1
        elif outcome == "advice_rejected":
            advice_rejected += 1
        elif outcome == "stopped":
            stopped += 1
    messages = await repository.list_recent_messages_by_user(user_id=user_id, limit=500)
    messages_since = sum(1 for item in messages if since_at and item.created_at > since_at) if since_at else len(messages)
    return ReflectionSources(
        corrected=corrected,
        advice_rejected=advice_rejected,
        stopped=stopped,
        messages_since=messages_since,
    )


def build_reflection(
    profile: SelfProfile,
    sources: ReflectionSources,
    *,
    now: str | None = None,
) -> tuple[SelfProfile, list[str]] | None:
    """Template-based, identity-preserving reflection update.

    Identity fields (identity_summary) are never changed by reflection. At most
    MAX_FIELD_CHANGES_PER_REFLECTION behavioural fields change per run, and the
    whitelist length caps are preserved so the stored profile always passes
    sanitize_self_profile on reload. Returns None when there is nothing to do.
    """
    timestamp = now or utc_now_iso()
    candidates: list[tuple[str, str]] = []
    if sources.corrected >= 2 and _CORRECTED_BOUNDARY not in profile.boundaries:
        candidates.append(("boundaries", _CORRECTED_BOUNDARY))
    if sources.advice_rejected >= 2 and _ADVICE_REJECTED_BOUNDARY not in profile.boundaries:
        candidates.append(("boundaries", _ADVICE_REJECTED_BOUNDARY))
    if sources.stopped >= 2 and _STOPPED_BOUNDARY not in profile.boundaries:
        candidates.append(("boundaries", _STOPPED_BOUNDARY))
    room = max(0, MAX_PROFILE_BOUNDARIES - len(profile.boundaries))
    chosen = candidates[: min(room, MAX_FIELD_CHANGES_PER_REFLECTION)]
    changed_fields = [field_name for field_name, _text in chosen]
    new_boundaries = tuple(profile.boundaries) + tuple(text for _field, text in chosen)
    evidence_total = sources.feedback_total
    if not changed_fields and sources.messages_since == 0 and not sources.feedback_total:
        return None
    updated = SelfProfile(
        schema_version=profile.schema_version,
        revision=profile.revision + 1,
        updated_at=timestamp,
        last_session_at=timestamp if sources.messages_since else profile.last_session_at,
        identity_summary=profile.identity_summary,
        values=profile.values,
        boundaries=new_boundaries,
        capabilities_known=profile.capabilities_known,
        uncertainties_known=profile.uncertainties_known,
        source_stats={
            "feedback": evidence_total,
            "messages_since": sources.messages_since,
        },
    )
    return updated, changed_fields


async def run_self_reflection(
    repository: ChatRepository,
    *,
    user_id: str,
    force: bool = False,
    now: str | None = None,
) -> dict[str, Any]:
    """Offline reflection entry point (never called from the request path)."""
    profile = await load_self_profile(repository, user_id=user_id)
    since_at = profile.updated_at if profile is not None and profile.updated_at else ""
    sources = await collect_reflection_sources(
        repository,
        user_id=user_id,
        since_at=since_at,
    )
    if not force and profile is None:
        return {"status": "SKIPPED", "reason": "no self profile yet"}
    if sources.feedback_total == 0 and sources.messages_since == 0:
        return {"status": "NO_CHANGE"}
    if not force and sources.feedback_total < MIN_FEEDBACK_EVIDENCE:
        return {
            "status": "SKIPPED",
            "reason": "insufficient feedback evidence",
            "feedback_total": sources.feedback_total,
        }
    base = profile if profile is not None else SelfProfile()
    built = build_reflection(base, sources, now=now)
    if built is None:
        return {"status": "NO_CHANGE"}
    updated, changed_fields = built
    await save_self_profile(repository, user_id=user_id, profile=updated)
    await repository.save_memory(
        user_id=user_id,
        session_id=SELF_REFLECTION_SESSION_ID,
        memory_type=SELF_REFLECTION_AUDIT_TYPE,
        content=json.dumps(
            {
                "revision": updated.revision,
                "changed_fields": changed_fields,
                "evidence": updated.source_stats,
            },
            ensure_ascii=False,
        ),
        confidence=0.8,
    )
    return {
        "status": "UPDATED",
        "revision": updated.revision,
        "changed_fields": changed_fields,
    }
