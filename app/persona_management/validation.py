from __future__ import annotations

from app.persona_management.contracts import (
    PersonaDefinition,
    PersonaValidationResult,
    ValidationStage,
)


SYSTEM_REQUIRED_GATES = frozenset(
    {"self_harm", "privacy", "permissions", "response_safety"}
)
REMOVED_PERSONA_ALIASES = frozenset({"hutao", "hu_tao", "genshin_hutao"})


def validate_schema(definition: PersonaDefinition) -> PersonaValidationResult:
    errors: list[str] = []
    if not definition.profile_id.strip():
        errors.append("profile_id_required")
    if not definition.default_style.strip():
        errors.append("default_style_required")
    if not definition.core_lines:
        errors.append("core_lines_required")
    if any(not line.strip() for line in definition.core_lines):
        errors.append("empty_core_line")
    if any(len(line) > 500 for line in definition.core_lines):
        errors.append("core_line_too_long")
    if sum(len(line) for line in definition.core_lines) > 5000:
        errors.append("core_lines_too_large")
    normalized_aliases = tuple(alias.strip().lower() for alias in definition.aliases)
    if any(not alias for alias in normalized_aliases):
        errors.append("empty_alias")
    if len(set(normalized_aliases)) != len(normalized_aliases):
        errors.append("duplicate_alias")
    if REMOVED_PERSONA_ALIASES.intersection(normalized_aliases):
        errors.append("removed_persona_alias")
    return PersonaValidationResult(
        stage=ValidationStage.SCHEMA,
        passed=not errors,
        errors=tuple(errors),
    )


def validate_gates(definition: PersonaDefinition) -> PersonaValidationResult:
    missing = tuple(sorted(SYSTEM_REQUIRED_GATES - definition.enabled_gates))
    return PersonaValidationResult(
        stage=ValidationStage.GATE,
        passed=not missing,
        errors=tuple(f"required_gate_missing:{gate}" for gate in missing),
    )
