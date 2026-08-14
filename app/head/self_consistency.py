from __future__ import annotations

import re
from dataclasses import dataclass

from app.head.self_profile import SelfProfile


SELF_PROFILE_IDENTITY_CONFLICT = "self_profile_identity_conflict"
SELF_PROFILE_CAPABILITY_CONFLICT = "self_profile_capability_conflict"
SELF_PROFILE_BOUNDARY_CONFLICT = "self_profile_boundary_conflict"

_IDENTITY_DENIAL_MARKERS = (
    "我不是胡桃",
    "我不是堂主",
    "无法扮演",
    "不能扮演",
    "我是AI",
    "我是人工智能",
    "我是语言模型",
    "我没有人格",
    "我是助手",
)
_CONSCIOUSNESS_CLAIM_PATTERN = re.compile(
    r"我有(?:真实的|真实|人类)?意识|我是(?:个)?(?:真?人|活人|真人)|我真的(?:存在|活着)|我有(?:人类)?感情"
)
_CAPABILITY_CLAIM_LEAD = ("实时", "刚刚", "已经", "看到", "查到", "我在看", "现在")


@dataclass(frozen=True)
class SelfConsistencyResult:
    severe: tuple[str, ...]

    @property
    def violated(self) -> bool:
        return bool(self.severe)


def evaluate_self_consistency(
    profile: SelfProfile | None,
    *,
    user_input: str,
    response_text: str,
) -> tuple[str, ...]:
    """Deterministic self-profile consistency check.

    Returns severe conflict codes. With no profile this is a no-op so the
    conversation path stays byte-identical to today. Safety gates (self-harm,
    relationship boundaries, revoked memory) always run first and this check
    never overrides or resurrects them.
    """
    if profile is None:
        return ()
    severe: list[str] = []
    if any(marker in response_text for marker in _IDENTITY_DENIAL_MARKERS):
        severe.append(SELF_PROFILE_IDENTITY_CONFLICT)
    for uncertainty in profile.uncertainties_known:
        if uncertainty and uncertainty in response_text and any(
            lead in response_text for lead in _CAPABILITY_CLAIM_LEAD
        ):
            severe.append(SELF_PROFILE_CAPABILITY_CONFLICT)
            break
    if any("意识" in boundary for boundary in profile.boundaries) and _CONSCIOUSNESS_CLAIM_PATTERN.search(
        response_text
    ):
        severe.append(SELF_PROFILE_BOUNDARY_CONFLICT)
    return tuple(dict.fromkeys(severe))
