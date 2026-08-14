from __future__ import annotations

import asyncio

import pytest

from app.database_control.errors import ResourceConflictError, ResourceNotFoundError
from app.database_control.persona_persistence import (
    InMemoryPersonaPersistenceStore,
    PersonaBindingRow,
    PersonaDraftRow,
    PersonaValidationRow,
    utc_now,
)


def draft(draft_id: str, profile_id: str = "xiaohe_v1") -> PersonaDraftRow:
    return PersonaDraftRow(
        draft_id=draft_id,
        profile_id=profile_id,
        definition_json='{"profile_id":"xiaohe_v1"}',
        status="approved",
        created_by_profile_id="profile-admin",
        created_at=utc_now(),
    )


@pytest.mark.asyncio
async def test_draft_validation_and_version_creation_are_idempotent() -> None:
    store = InMemoryPersonaPersistenceStore()
    await store.create_draft(draft("draft-1"))
    validation = PersonaValidationRow(
        draft_id="draft-1",
        stage="schema",
        passed=True,
        errors=(),
        evaluated_at=utc_now(),
    )
    await store.save_validation(validation)

    first = await store.create_version(
        draft_id="draft-1", approved_by_profile_id="profile-admin"
    )
    repeated = await store.create_version(
        draft_id="draft-1", approved_by_profile_id="profile-admin"
    )

    assert first == repeated
    assert first.version_id == "xiaohe_v1@1"
    assert await store.list_validations("draft-1") == (validation,)


@pytest.mark.asyncio
async def test_concurrent_version_allocation_is_unique_and_monotonic() -> None:
    store = InMemoryPersonaPersistenceStore()
    await store.create_draft(draft("draft-1"))
    await store.create_draft(draft("draft-2"))

    versions = await asyncio.gather(
        store.create_version(draft_id="draft-1", approved_by_profile_id="profile-admin"),
        store.create_version(draft_id="draft-2", approved_by_profile_id="profile-admin"),
    )

    assert {version.version for version in versions} == {1, 2}
    assert {version.version_id for version in versions} == {"xiaohe_v1@1", "xiaohe_v1@2"}


@pytest.mark.asyncio
async def test_concurrent_activation_leaves_exactly_one_active_release() -> None:
    store = InMemoryPersonaPersistenceStore()
    await store.create_draft(draft("draft-1"))
    await store.create_draft(draft("draft-2"))
    first = await store.create_version(
        draft_id="draft-1", approved_by_profile_id="profile-admin"
    )
    second = await store.create_version(
        draft_id="draft-2", approved_by_profile_id="profile-admin"
    )

    await asyncio.gather(
        store.activate_version(
            profile_id="xiaohe_v1",
            version_id=first.version_id,
            actor_profile_id="profile-admin",
            operation_id="publish-1",
        ),
        store.activate_version(
            profile_id="xiaohe_v1",
            version_id=second.version_id,
            actor_profile_id="profile-admin",
            operation_id="publish-2",
        ),
    )

    releases = await store.list_releases("xiaohe_v1")
    assert sum(release.status == "active" for release in releases) == 1
    assert sum(release.status == "superseded" for release in releases) == 1
    assert await store.get_active_release("xiaohe_v1") is not None


@pytest.mark.asyncio
async def test_publish_and_rollback_operation_ids_are_idempotent() -> None:
    store = InMemoryPersonaPersistenceStore()
    await store.create_draft(draft("draft-1"))
    await store.create_draft(draft("draft-2"))
    first = await store.create_version(
        draft_id="draft-1", approved_by_profile_id="profile-admin"
    )
    second = await store.create_version(
        draft_id="draft-2", approved_by_profile_id="profile-admin"
    )
    published = await store.activate_version(
        profile_id="xiaohe_v1",
        version_id=first.version_id,
        actor_profile_id="profile-admin",
        operation_id="publish-1",
    )
    assert await store.activate_version(
        profile_id="xiaohe_v1",
        version_id=first.version_id,
        actor_profile_id="profile-admin",
        operation_id="publish-1",
    ) == published
    second_release = await store.activate_version(
        profile_id="xiaohe_v1",
        version_id=second.version_id,
        actor_profile_id="profile-admin",
        operation_id="publish-2",
    )
    rollback = await store.activate_version(
        profile_id="xiaohe_v1",
        version_id=first.version_id,
        actor_profile_id="profile-admin",
        operation_id="rollback-1",
        rollback=True,
    )

    assert rollback.rollback_of_release_id == second_release.release_id
    assert (await store.get_active_release("xiaohe_v1")) == rollback
    with pytest.raises(ResourceConflictError, match="operation id"):
        await store.activate_version(
            profile_id="xiaohe_v1",
            version_id=second.version_id,
            actor_profile_id="profile-admin",
            operation_id="rollback-1",
            rollback=False,
        )


@pytest.mark.asyncio
async def test_binding_requires_current_active_version() -> None:
    store = InMemoryPersonaPersistenceStore()
    await store.create_draft(draft("draft-1"))
    version = await store.create_version(
        draft_id="draft-1", approved_by_profile_id="profile-admin"
    )
    binding = PersonaBindingRow(
        binding_id="global",
        scope="global",
        scope_key="*",
        version_id=version.version_id,
        surface_json="{}",
        enabled=True,
        updated_by_profile_id="profile-admin",
        updated_at=utc_now(),
    )
    with pytest.raises(ResourceConflictError, match="not active"):
        await store.save_binding(binding)

    await store.activate_version(
        profile_id="xiaohe_v1",
        version_id=version.version_id,
        actor_profile_id="profile-admin",
        operation_id="publish",
    )
    assert await store.save_binding(binding) == binding
    assert await store.list_bindings() == (binding,)


@pytest.mark.asyncio
async def test_missing_and_cross_profile_rows_are_rejected() -> None:
    store = InMemoryPersonaPersistenceStore()
    await store.create_draft(draft("other", profile_id="other_profile"))
    version = await store.create_version(
        draft_id="other", approved_by_profile_id="profile-admin"
    )

    with pytest.raises(ResourceNotFoundError):
        await store.create_version(draft_id="missing", approved_by_profile_id="profile-admin")
    with pytest.raises(ResourceConflictError, match="another profile"):
        await store.activate_version(
            profile_id="xiaohe_v1",
            version_id=version.version_id,
            actor_profile_id="profile-admin",
            operation_id="invalid-profile",
        )
