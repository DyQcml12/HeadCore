from __future__ import annotations

from datetime import datetime
from typing import Protocol


class EmailVerificationDelivery(Protocol):
    """External delivery boundary. Implementations must not log the raw token."""

    async def send_verification(self, *, email: str, token: str, expires_at: datetime) -> None: ...


class PasswordResetDelivery(Protocol):
    """External delivery boundary. Implementations must not log the raw token."""

    async def send_password_reset(self, *, email: str, token: str, expires_at: datetime) -> None: ...
