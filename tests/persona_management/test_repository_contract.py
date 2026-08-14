from __future__ import annotations

from app.persona_management import (
    InMemoryPersonaManagementRepository,
    PersonaDefinition,
    PersonaDraft,
    PersonaValidationResult,
    SYSTEM_REQUIRED_GATES,
    ValidationStage,
)


def test_repository_returns_validation_snapshot_not_mutable_internal_state() -> None:
    repository = InMemoryPersonaManagementRepository()
    draft = PersonaDraft(
        draft_id="draft",
        definition=PersonaDefinition(
            profile_id="xiaohe_v1",
            aliases=("xiaohe_v1",),
            default_style="自然",
            core_lines=("保持边界",),
            enabled_gates=SYSTEM_REQUIRED_GATES,
        ),
    )
    repository.save_draft(draft)
    result = PersonaValidationResult(stage=ValidationStage.SCHEMA, passed=True)
    repository.save_validation(draft.draft_id, result)

    snapshot = repository.get_validations(draft.draft_id)
    snapshot.clear()

    assert repository.get_validations(draft.draft_id) == {ValidationStage.SCHEMA: result}
