from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.head.reflection_loop import (
    ReflectionSources,
    build_reflection,
    collect_reflection_sources,
    run_self_reflection,
)
from app.head.self_profile import SelfProfile, sanitize_self_profile, utc_now_iso
from app.head.self_profile_store import load_self_profile, save_self_profile
from app.storage.chat_repository import JsonlChatRepository

def _profile(boundaries=None, updated_at=""):
    return sanitize_self_profile(
        {
            "schema_version": 1,
            "revision": 1,
            "updated_at": updated_at,
            "identity_summary": "我是胡桃，往生堂第七十七代堂主。",
            "boundaries": boundaries or [],
            "capabilities_known": ["文字聊天"],
        }
    )


async def _save_feedback(repository, user_id, outcome):
    await repository.save_memory(
        user_id=user_id,
        session_id="s1",
        memory_type="head_feedback",
        content=json.dumps({"previous_action": "x", "outcome": outcome, "signals": []}),
        confidence=0.8,
    )

def test_reflection_never_changes_identity_summary():
    profile = _profile()
    sources = ReflectionSources(corrected=2, advice_rejected=0, stopped=0, messages_since=5)

    built = build_reflection(profile, sources, now="2026-08-14T00:00:00+00:00")

    assert built is not None
    updated, changed = built
    assert updated.identity_summary == profile.identity_summary
    assert updated.revision == 2
    assert any("被指出" in boundary for boundary in updated.boundaries)


def test_reflection_respects_boundary_cap():
    profile = _profile(boundaries=["b1", "b2", "b3", "b4", "b5"])
    sources = ReflectionSources(corrected=2, advice_rejected=2, stopped=2, messages_since=3)

    built = build_reflection(profile, sources, now=utc_now_iso())

    assert built is not None
    updated, changed = built
    assert len(updated.boundaries) == 5
    assert changed == []
    assert updated.source_stats == {"feedback": 6, "messages_since": 3}


def test_reflection_no_op_returns_none():
    profile = _profile()
    sources = ReflectionSources(corrected=0, advice_rejected=0, stopped=0, messages_since=0)

    assert build_reflection(profile, sources) is None

def test_run_reflection_skips_without_enough_evidence(tmp_path: Path):
    repository = JsonlChatRepository(tmp_path / "storage")
    asyncio.run(save_self_profile(repository, user_id="u1", profile=_profile()))
    asyncio.run(_save_feedback(repository, "u1", "corrected"))

    result = asyncio.run(run_self_reflection(repository, user_id="u1"))

    assert result["status"] == "SKIPPED"


def test_run_reflection_updates_and_writes_audit(tmp_path: Path):
    repository = JsonlChatRepository(tmp_path / "storage")
    asyncio.run(save_self_profile(repository, user_id="u1", profile=_profile()))
    for _ in range(2):
        asyncio.run(_save_feedback(repository, "u1", "corrected"))
    asyncio.run(_save_feedback(repository, "u1", "stopped"))

    result = asyncio.run(run_self_reflection(repository, user_id="u1"))

    assert result["status"] == "UPDATED"
    loaded = asyncio.run(load_self_profile(repository, user_id="u1"))
    assert loaded is not None
    assert loaded.revision == 2
    assert any("被指出问题" in boundary for boundary in loaded.boundaries)
    audits = asyncio.run(
        repository.list_memories(user_id="u1", memory_types=["head_reflection_audit"], limit=10)
    )
    assert audits
    assert json.loads(audits[-1].content)["revision"] == 2


def test_run_reflection_is_idempotent(tmp_path: Path):
    repository = JsonlChatRepository(tmp_path / "storage")
    asyncio.run(save_self_profile(repository, user_id="u1", profile=_profile()))
    for _ in range(3):
        asyncio.run(_save_feedback(repository, "u1", "advice_rejected"))

    first = asyncio.run(run_self_reflection(repository, user_id="u1"))
    second = asyncio.run(run_self_reflection(repository, user_id="u1"))

    assert first["status"] == "UPDATED"
    assert second["status"] == "NO_CHANGE"
