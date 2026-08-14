from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Iterable

from app.operations.contracts import ErrorSummary


_CATEGORIES = (
    ("timeout", re.compile(r"timeout|timed out", re.IGNORECASE)),
    ("authentication", re.compile(r"unauthorized|forbidden|auth(?:entication)? failed|\b401\b|\b403\b", re.IGNORECASE)),
    ("rate_limit", re.compile(r"rate.?limit|too many requests|\b429\b", re.IGNORECASE)),
    ("connection", re.compile(r"connection (?:refused|reset|closed)|network unreachable", re.IGNORECASE)),
    ("database", re.compile(r"mysql|database|deadlock|sqlstate", re.IGNORECASE)),
    ("provider", re.compile(r"provider|model unavailable|upstream", re.IGNORECASE)),
    ("channel", re.compile(r"websocket|gateway", re.IGNORECASE)),
    ("configuration", re.compile(r"not configured|missing config|configuration", re.IGNORECASE)),
    ("validation", re.compile(r"invalid|validation|malformed|unsupported", re.IGNORECASE)),
)


def classify_error_lines(lines: Iterable[str], *, latest_at: datetime | None = None) -> tuple[ErrorSummary, ...]:
    counts: Counter[str] = Counter()
    for line in lines:
        category = "unknown"
        for candidate, pattern in _CATEGORIES:
            if pattern.search(line):
                category = candidate
                break
        counts[category] += 1
    return tuple(
        ErrorSummary(category=category, count=count, latest_at=latest_at)
        for category, count in sorted(counts.items())
    )
