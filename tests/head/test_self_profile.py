from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.head.self_profile import (
    SELF_PROFILE_MEMORY_TYPE,
    SelfProfile,
    render_self_profile_projection,
    sanitize_self_profile,
    self_profile_from_json,
    self_profile_to_json,
    utc_now_iso,
)
from app.head.self_profile_store import load_self_profile, reset_self_profile, save_self_profile
from app.storage.chat_repository import JsonlChatRepository


def _valid_raw() -> dict[str, object]:
    return {
        "schema_version": 1,
        "revision": 2,
        "updated_at": utc_now_iso(),
        "last_session_at": utc_now_iso(),
        "identity_summary": "我是胡桃，往生堂第七十七代堂主，与旅行者是旧识。",
        "values": ["回复短而自然", "关系有边界"],
        "boundaries": ["不证明自己有真实意识", "不猜测用户隐私"],
        "capabilities_known": ["文字聊天", "记忆读取"],
        "uncertainties_known": ["实时新闻"],
        "source_stats": {"feedback": 3, "sessions": 5},
    }


def test_sanitize_keeps_only_whitelisted_fields_and_drops_unknown() -> None:
    raw = {**_valid_raw(), "user_real_name": "阿明", "internal_secret": "x"}

    profile = sanitize_self_profile(raw)

    assert profile.revision == 2
    assert "阿明" not in profile.identity_summary
    assert profile.values == ("回复短而自然", "关系有边界")
    assert profile.boundaries == ("不证明自己有真实意识", "不猜测用户隐私")
    assert profile.source_stats == {"feedback": 3, "sessions": 5}
    assert "user_real_name" not in profile.to_dict()


def test_sanitize_rejects_overlong_and_wrong_types() -> None:
    with pytest.raises(ValueError):
        sanitize_self_profile({**_valid_raw(), "identity_summary": "长" * 200})
    with pytest.raises(ValueError):
        sanitize_self_profile({**_valid_raw(), "values": ["a"] * 6})
    with pytest.raises(ValueError):
        sanitize_self_profile({**_valid_raw(), "revision": 0})
    with pytest.raises(ValueError):
        sanitize_self_profile({**_valid_raw(), "source_stats": {"x": -1}})


def test_profile_roundtrip_through_json() -> None:
    profile = sanitize_self_profile(_valid_raw())

    restored = self_profile_from_json(self_profile_to_json(profile))

    assert restored == profile


def test_corrupted_profile_parses_to_none() -> None:
    assert self_profile_from_json("not json") is None
    assert self_profile_from_json(json.dumps({"schema_version": 99})) is None


def test_save_load_latest_and_reset(tmp_path: Path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    first = sanitize_self_profile(_valid_raw())
    second = sanitize_self_profile({**_valid_raw(), "revision": 3, "identity_summary": "稳定人格身份是胡桃。"})

    asyncio.run(save_self_profile(repository, user_id="u1", profile=first))
    asyncio.run(save_self_profile(repository, user_id="u1", profile=second))

    loaded = asyncio.run(load_self_profile(repository, user_id="u1"))
    assert loaded is not None
    assert loaded.revision == 3
    assert loaded.identity_summary == "稳定人格身份是胡桃。"
    assert asyncio.run(load_self_profile(repository, user_id="u2")) is None

    deleted = asyncio.run(reset_self_profile(repository, user_id="u1"))
    assert deleted == 2
    assert asyncio.run(load_self_profile(repository, user_id="u1")) is None


def test_self_profile_memory_is_internal_only(tmp_path: Path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    asyncio.run(save_self_profile(repository, user_id="u1", profile=sanitize_self_profile(_valid_raw())))

    visible = asyncio.run(repository.list_memories(user_id="u1", limit=50))

    assert all(record.memory_type != SELF_PROFILE_MEMORY_TYPE for record in visible)


def test_render_projection_is_empty_without_profile() -> None:
    assert render_self_profile_projection(None) == ""


def test_render_projection_includes_summary_and_time() -> None:
    profile = sanitize_self_profile(_valid_raw())

    rendered = render_self_profile_projection(profile, now=profile.updated_at)

    assert "身份一致性要点" in rendered
    assert "不向用户复述" in rendered
    assert "不宣称意识" in rendered
    assert "上次对话" in rendered
