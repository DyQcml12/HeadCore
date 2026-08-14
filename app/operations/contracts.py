from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping


class ComponentState(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    MISSING = "missing"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class DependencyStatus:
    component_id: str
    state: ComponentState
    blocking_reason: str = ""


@dataclass(frozen=True)
class ComponentStatus:
    component_id: str
    label: str
    state: ComponentState
    category: str
    detail: str = ""
    dependencies: tuple[DependencyStatus, ...] = ()
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class OperationResult:
    action: str
    actor_id: str
    occurred_at: datetime
    success: bool
    audit_id: str
    reason: str = ""


@dataclass(frozen=True)
class TestReportSummary:
    suite: str
    passed: int
    failed: int
    report_path: str
    timestamp: datetime
    state: ComponentState = ComponentState.ONLINE
    detail: str = ""


@dataclass(frozen=True)
class RedactedConfigStatus:
    name: str
    configured: bool


@dataclass(frozen=True)
class ErrorSummary:
    category: str
    count: int
    latest_at: datetime | None = None


@dataclass(frozen=True)
class OperationsSnapshot:
    state: ComponentState
    components: Mapping[str, ComponentStatus]
    generated_at: datetime

