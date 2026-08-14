from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.operations.contracts import OperationResult
from app.operations.redaction import redact_text


class OperationPermissionError(PermissionError):
    status_code = 403


class OperationAuthorizer:
    @staticmethod
    def require_admin(*, actor_id: str, is_admin: bool) -> None:
        if not actor_id or not is_admin:
            raise OperationPermissionError("administrator actor required")


class InMemoryOperationAudit:
    def __init__(self) -> None:
        self._records: list[OperationResult] = []

    def record(
        self,
        *,
        action: str,
        actor_id: str,
        is_admin: bool,
        success: bool,
        reason: str = "",
    ) -> OperationResult:
        OperationAuthorizer.require_admin(actor_id=actor_id, is_admin=is_admin)
        result = OperationResult(
            action=action,
            actor_id=actor_id,
            occurred_at=datetime.now(timezone.utc),
            success=success,
            audit_id=uuid4().hex,
            reason=redact_text(reason),
        )
        self._records.append(result)
        return result

    def list_records(self) -> tuple[OperationResult, ...]:
        return tuple(self._records)
