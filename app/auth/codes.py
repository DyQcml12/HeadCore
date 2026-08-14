from __future__ import annotations

import secrets


def new_six_digit_code() -> str:
    """Return a zero-padded six-digit numeric code for emailed verification.

    Codes are single-use and expire quickly, and the confirmation endpoints
    are rate-limited, so a six-digit space is sufficient for local use.
    """
    return f"{secrets.randbelow(1_000_000):06d}"
