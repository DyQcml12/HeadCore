from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DraftStatus(StrEnum):
    DRAFT = "draft"
    SCHEMA_VALIDATED = "schema_validated"
    OFFLINE_EVALUATED = "offline_evaluated"
    APPROVED = "approved"
    PUBLISHED = "published"


class ReleaseStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"
    ARCHIVED = "archived"


class ValidationStage(StrEnum):
    SCHEMA = "schema"
    GATE = "gate"
    REGRESSION = "regression"
    LIVE_ACCEPTANCE = "live_acceptance"


class BindingScope(StrEnum):
    GLOBAL = "global"
    PLATFORM = "platform"
    RELATIONSHIP = "relationship"
    PROFILE = "profile"
    CONVERSATION = "conversation"


@dataclass(frozen=True)
class PersonaDefinition:
    profile_id: str
    aliases: tuple[str, ...]
    default_style: str
    core_lines: tuple[str, ...]
    enabled_gates: frozenset[str]


@dataclass(frozen=True)
class PersonaDraft:
    draft_id: str
    definition: PersonaDefinition
    status: DraftStatus = DraftStatus.DRAFT
    created_by: str = "system"
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PersonaVersion:
    profile_id: str
    version: int
    definition: PersonaDefinition
    source_draft_id: str
    approved_by: str
    created_at: datetime = field(default_factory=utc_now)

    @property
    def version_id(self) -> str:
        return f"{self.profile_id}@{self.version}"


@dataclass(frozen=True)
class PersonaRelease:
    release_id: str
    version_id: str
    status: ReleaseStatus
    actor_id: str
    created_at: datetime = field(default_factory=utc_now)
    replaced_release_id: str | None = None
    rollback_of_release_id: str | None = None


@dataclass(frozen=True)
class PersonaBinding:
    binding_id: str
    scope: BindingScope
    scope_key: str
    version_id: str
    surface: tuple[tuple[str, str], ...] = ()
    active: bool = True


@dataclass(frozen=True)
class PersonaValidationResult:
    stage: ValidationStage
    passed: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class BindingContext:
    platform: str = ""
    relationship: str = ""
    profile_id: str = ""
    conversation_id: str = ""


@dataclass(frozen=True)
class PersonaRuntimeProjection:
    profile_id: str
    version: int
    version_id: str
    default_style: str
    core_lines: tuple[str, ...]
    effective_gates: frozenset[str]
    surface: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PersonaManagementStatus:
    storage_backend: str
    durable: bool
    write_ready: bool
    draft_count: int
    version_count: int
    release_count: int
    binding_count: int
    active_profiles: tuple[str, ...]
