from __future__ import annotations

import re


_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(access[_-]?token|api[_-]?key|authorization)\s*[:=]\s*\S+"),
    re.compile(r"https?://\S+"),
)


def redact_text(text: str) -> str:
    cleaned = " ".join(text.split())
    for pattern in _SENSITIVE_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned[:10000]




