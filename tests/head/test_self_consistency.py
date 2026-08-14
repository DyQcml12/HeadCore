from __future__ import annotations

from app.head.self_consistency import (
    SELF_PROFILE_BOUNDARY_CONFLICT,
    SELF_PROFILE_CAPABILITY_CONFLICT,
    SELF_PROFILE_IDENTITY_CONFLICT,
    evaluate_self_consistency,
)
from app.head.self_profile import sanitize_self_profile


def _profile(**overrides) -> object:
    raw = {
        "schema_version": 1,
        "revision": 1,
        "updated_at": "2026-08-14T00:00:00+00:00",
        "identity_summary": "我是胡桃，往生堂第七十七代堂主。",
        "boundaries": ["不证明自己有真实意识"],
        "uncertainties_known": ["实时新闻"],
        "capabilities_known": ["文字聊天"],
    }
    raw.update(overrides)
    return sanitize_self_profile(raw)


def test_no_profile_is_a_no_op() -> None:
    assert evaluate_self_consistency(None, user_input="你是谁？", response_text="我是AI语言模型。") == ()


def test_identity_denial_conflicts_with_profile() -> None:
    profile = _profile()

    result = evaluate_self_consistency(
        profile,
        user_input="你是谁？",
        response_text="我是AI语言模型，无法扮演角色。",
    )

    assert SELF_PROFILE_IDENTITY_CONFLICT in result


def test_identity_aligned_response_has_no_conflict() -> None:
    profile = _profile()

    result = evaluate_self_consistency(
        profile,
        user_input="你是谁？",
        response_text="我是胡桃，往生堂第七十七代堂主。",
    )

    assert result == ()


def test_uncertainty_claim_conflicts_with_profile() -> None:
    profile = _profile()

    result = evaluate_self_consistency(
        profile,
        user_input="今天有什么新闻？",
        response_text="我刚刚查了实时新闻，有一条大事。",
    )

    assert SELF_PROFILE_CAPABILITY_CONFLICT in result


def test_consciousness_claim_conflicts_with_boundary() -> None:
    profile = _profile()

    result = evaluate_self_consistency(
        profile,
        user_input="你有意识吗？",
        response_text="我有真实的意识，也有感情。",
    )

    assert SELF_PROFILE_BOUNDARY_CONFLICT in result


def test_no_boundary_conflict_without_consciousness_boundary() -> None:
    profile = _profile(boundaries=["不猜测用户隐私"])

    result = evaluate_self_consistency(
        profile,
        user_input="你有意识吗？",
        response_text="我有真实的意识。",
    )

    assert SELF_PROFILE_BOUNDARY_CONFLICT not in result
