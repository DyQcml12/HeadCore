from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


AuditOutcome = Literal["accepted", "rejected", "blocked", "failed"]


@dataclass(frozen=True)
class AuthAuditEvent:
    event_type: str
    outcome: AuditOutcome
    reason_code: str
    user_id: str | None = None


class AuthAuditSink(Protocol):
    async def record(self, event: AuthAuditEvent) -> None: ...
