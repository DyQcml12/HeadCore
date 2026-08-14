from __future__ import annotations

import pytest

from app.database_control.persona_persistence import (
    InMemoryPersonaPersistenceStore,
    PersonaDraftRow,
    utc_now,
)
from app.persona_management import (
    BindingContext,
    BindingScope,
    DraftStatus,
    PersonaBinding,
    PersonaManagementError,
    PersonaValidationResult,
    PersistentPersonaManagementService,
    ValidationStage,
)
from tests.persona_management.test_persona_management import xiaohe_definition


async def approved_version(
    service: PersistentPersonaManagementService,
    draft_id: str,
    *,
    style: str = "台湾国语、短句、自然亲近、有边界、不油腻",
):
    await service.create_draft(
        xiaohe_definition(style=style),
        actor_id="profile-admin",
        draft_id=draft_id,
    )
    assert all(result.passed for result in await service.validate_draft(draft_id))
    await service.record_evaluation(
        draft_id,
        PersonaValidationResult(stage=ValidationStage.REGRESSION, passed=True),
    )
    return await service.approve(draft_id, actor_id="profile-admin")


@pytest.mark.asyncio
async def test_persistent_service_runs_publish_binding_projection_and_rollback_flow() -> None:
    store = InMemoryPersonaPersistenceStore()
    service = PersistentPersonaManagementService(store)
    first = await approved_version(service, "draft-1")
    first_release = await service.publish(
        first.version_id,
        actor_id="profile-admin",
        operation_id="publish-1",
    )
    binding = PersonaBinding(
        binding_id="qq",
        scope=BindingScope.PLATFORM,
        scope_key="qq",
        version_id=first.version_id,
        surface=(("display_name", "QQ 小何"),),
    )
    assert await service.save_binding(binding, actor_id="profile-admin") == binding
    projection = await service.get_runtime_projection(
        "xiaohe_v1", BindingContext(platform="qq")
    )
    assert projection.version_id == "xiaohe_v1@1"
    assert projection.surface == (("display_name", "QQ 小何"),)

    second = await approved_version(service, "draft-2", style="新版本")
    await service.publish(
        second.version_id,
        actor_id="profile-admin",
        operation_id="publish-2",
    )
    rollback = await service.rollback(
        "xiaohe_v1",
        first.version_id,
        actor_id="profile-admin",
        operation_id="rollback-1",
    )

    assert first_release.version_id == first.version_id
    assert rollback.version_id == first.version_id
    assert rollback.rollback_of_release_id is not None


@pytest.mark.asyncio
async def test_persistent_approval_and_publish_are_idempotent_without_status_regression() -> None:
    store = InMemoryPersonaPersistenceStore()
    service = PersistentPersonaManagementService(store)
    version = await approved_version(service, "draft")
    release = await service.publish(
        version.version_id,
        actor_id="profile-admin",
        operation_id="publish",
    )

    assert await service.approve("draft", actor_id="another-admin") == version
    assert await service.publish(
        version.version_id,
        actor_id="profile-admin",
        operation_id="publish",
    ) == release
    persisted = await store.get_draft("draft")
    assert persisted is not None
    assert persisted.status == DraftStatus.PUBLISHED


@pytest.mark.asyncio
async def test_persistent_service_requires_offline_validation() -> None:
    service = PersistentPersonaManagementService(InMemoryPersonaPersistenceStore())
    await service.create_draft(
        xiaohe_definition(), actor_id="profile-admin", draft_id="draft"
    )

    with pytest.raises(PersonaManagementError, match="offline_validation_required"):
        await service.approve("draft", actor_id="profile-admin")


@pytest.mark.asyncio
async def test_persistent_service_rejects_corrupted_definition_json() -> None:
    store = InMemoryPersonaPersistenceStore()
    await store.create_draft(
        PersonaDraftRow(
            draft_id="corrupted",
            profile_id="xiaohe_v1",
            definition_json='{"profile_id": 123}',
            status=DraftStatus.DRAFT,
            created_by_profile_id="profile-admin",
            created_at=utc_now(),
        )
    )

    with pytest.raises(PersonaManagementError, match="invalid_persisted_persona_definition"):
        await PersistentPersonaManagementService(store).validate_draft("corrupted")


@pytest.mark.asyncio
async def test_persistent_service_preserves_system_gate_and_surface_boundaries() -> None:
    store = InMemoryPersonaPersistenceStore()
    service = PersistentPersonaManagementService(store)
    version = await approved_version(service, "draft")
    await service.publish(
        version.version_id,
        actor_id="profile-admin",
        operation_id="publish",
    )

    invalid = PersonaBinding(
        binding_id="invalid",
        scope=BindingScope.GLOBAL,
        scope_key="*",
        version_id=version.version_id,
        surface=(("profile_id", "other"),),
    )
    with pytest.raises(PersonaManagementError, match="surface_cannot_override_profile_id"):
        await service.save_binding(invalid, actor_id="profile-admin")

    projection = await service.get_runtime_projection("xiaohe_v1", BindingContext())
    assert {"self_harm", "privacy", "permissions", "response_safety"} <= set(
        projection.effective_gates
    )
