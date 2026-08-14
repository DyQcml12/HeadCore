from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AsrQuality:
    passed: bool
    score: float
    reasons: list[str]
    character_count: int
    cjk_ratio: float


MOJIBAKE_MARKERS = ("�", "锟", "ï", "¿", "½", "Ã")


def evaluate_asr_text_quality(text: str) -> AsrQuality:
    clean = text.strip()
    reasons: list[str] = []
    meaningful_chars = [char for char in clean if not char.isspace()]
    character_count = len(meaningful_chars)
    cjk_count = sum(1 for char in meaningful_chars if "\u4e00" <= char <= "\u9fff")
    cjk_ratio = round(cjk_count / character_count, 3) if character_count else 0.0

    if not clean:
        reasons.append("empty_transcript")
    if character_count and character_count < 2:
        reasons.append("too_short")
    if character_count >= 4 and cjk_ratio < 0.35:
        reasons.append("low_chinese_ratio")
    if any(marker in clean for marker in MOJIBAKE_MARKERS):
        reasons.append("mojibake_or_replacement_char")
    if re.search(r"(.)\1{5,}", clean):
        reasons.append("excessive_repetition")
    if character_count and not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", clean):
        reasons.append("punctuation_only")
    if re.search(r"[，,][。.!！？?]", clean) or re.search(r"[。.!！？?][，,]", clean):
        reasons.append("punctuation_collision")

    score = 1.0
    score -= 0.35 * len(set(reasons))
    if character_count >= 4:
        score -= max(0.0, 0.5 - cjk_ratio) * 0.5
    score = round(max(0.0, min(1.0, score)), 3)
    return AsrQuality(
        passed=not reasons,
        score=score,
        reasons=reasons,
        character_count=character_count,
        cjk_ratio=cjk_ratio,
    )
