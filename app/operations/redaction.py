from __future__ import annotations

import re
from collections.abc import Mapping

from app.operations.contracts import RedactedConfigStatus


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|token|password|passwd|secret|authorization)\b(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*")
_OPENAI_STYLE_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def redact_text(text: str) -> str:
    redacted = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}<REDACTED>", text)
    redacted = _BEARER.sub("Bearer <REDACTED>", redacted)
    return _OPENAI_STYLE_KEY.sub("<REDACTED>", redacted)


def config_presence(values: Mapping[str, str | None]) -> tuple[RedactedConfigStatus, ...]:
    return tuple(
        RedactedConfigStatus(name=name, configured=bool(value and value.strip()))
        for name, value in sorted(values.items())
    )
