from __future__ import annotations

import re


SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9]{20,}")


def redact_secrets(text: str) -> str:
    return SECRET_PATTERN.sub("<REDACTED_API_KEY>", text)
