from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.persona_management import (
    BindingContext,
    BindingScope,
    DraftStatus,
    InMemoryPersonaManagementService,
    InMemoryPersonaManagementRepository,
    PersonaBinding,
    PersonaDefinition,
    PersonaManagementError,
    PersonaRuntimeProjection,
    PersonaValidationResult,
    ReleaseStatus,
    SYSTEM_REQUIRED_GATES,
    ValidationStage,
    build_runtime_projection,
    resolve_binding,
)


def xiaohe_definition(*, style: str = "台湾国语、短句、自然亲近、有边界、不油腻") -> PersonaDefinition:
    return PersonaDefinition(
        profile_id="xiaohe_v1",
        aliases=("xiaohe_v1", "xiaohe", "taiwan_girlfriend_xiaohe", "nameless_xiaohe"),
        default_style=style,
        core_lines=(
            "稳定人格是小何：会认真听人说话，短句自然，亲近但不油腻。",
            "普通朋友面前保持友好边界；只有管理员/爱人关系里才可以更偏心、更亲密。",
        ),
        enabled_gates=SYSTEM_REQUIRED_GATES | {"legacy_identity_leak"},
    )


def approved_version(
    service: InMemoryPersonaManagementService,
    *,
    draft_id: str,
    style: str = "台湾国语、短句、自然亲近、有边界、不油腻",
):
    service.create_draft(xiaohe_definition(style=style), actor_id="author", draft_id=draft_id)
    assert all(result.passed for result in service.validate_draft(draft_id))
    service.record_evaluation(
        draft_id,
        PersonaValidationResult(stage=ValidationStage.REGRESSION, passed=True),
    )
    return service.approve(draft_id, actor_id="reviewer")


def test_single_profile_can_publish_and_rollback_idempotently() -> None:
    service = InMemoryPersonaManagementService()
    version_1 = approved_version(service, draft_id="draft-1")
    release_1 = service.publish(version_1.version_id, actor_id="operator")
    assert service.publish(version_1.version_id, actor_id="operator") == release_1

    version_2 = approved_version(service, draft_id="draft-2", style="更清楚、更克制")
    release_2 = service.publish(version_2.version_id, actor_id="operator")
    rollback = service.rollback("xiaohe_v1", version_1.version_id, actor_id="operator")

    assert service.rollback("xiaohe_v1", version_1.version_id, actor_id="operator") == rollback
    assert service.get_active_version("xiaohe_v1") == version_1
    releases = service.list_releases("xiaohe_v1")
    assert [release.status for release in releases] == [
        ReleaseStatus.SUPERSEDED,
        ReleaseStatus.ROLLED_BACK,
        ReleaseStatus.ACTIVE,
    ]
    assert release_2.release_id == rollback.rollback_of_release_id

    archived = service.archive(release_2.release_id)
    assert archived.status == ReleaseStatus.ARCHIVED
    assert service.archive(release_2.release_id) == archived
    with pytest.raises(PersonaManagementError, match="active_release_cannot_be_archived"):
        service.archive(rollback.release_id)


def test_draft_requires_validation_and_cannot_be_runtime_projection() -> None:
    service = InMemoryPersonaManagementService()
    draft = service.create_draft(xiaohe_definition(), actor_id="author", draft_id="draft")

    with pytest.raises(PersonaManagementError, match="offline_validation_required"):
        service.approve(draft.draft_id, actor_id="reviewer")
    with pytest.raises(AttributeError):
        build_runtime_projection(draft)  # type: ignore[arg-type]

    service.validate_draft(draft.draft_id)
    with pytest.raises(PersonaManagementError, match="offline_validation_required"):
        service.approve(draft.draft_id, actor_id="reviewer")


def test_required_system_gate_cannot_be_disabled() -> None:
    definition = xiaohe_definition()
    unsafe = PersonaDefinition(
        profile_id=definition.profile_id,
        aliases=definition.aliases,
        default_style=definition.default_style,
        core_lines=definition.core_lines,
        enabled_gates=frozenset({"privacy"}),
    )
    service = InMemoryPersonaManagementService()
    service.create_draft(unsafe, actor_id="author", draft_id="unsafe")

    results = service.validate_draft("unsafe")

    gate_result = next(result for result in results if result.stage == ValidationStage.GATE)
    assert gate_result.passed is False
    assert "required_gate_missing:self_harm" in gate_result.errors
    with pytest.raises(PersonaManagementError, match="offline_validation_required"):
        service.approve("unsafe", actor_id="reviewer")


@pytest.mark.parametrize("alias", ["hutao", "hu_tao", "genshin_hutao"])
def test_removed_legacy_alias_is_rejected(alias: str) -> None:
    definition = xiaohe_definition()
    invalid = PersonaDefinition(
        profile_id=definition.profile_id,
        aliases=definition.aliases + (alias,),
        default_style=definition.default_style,
        core_lines=definition.core_lines,
        enabled_gates=definition.enabled_gates,
    )
    service = InMemoryPersonaManagementService()
    service.create_draft(invalid, actor_id="author", draft_id=alias)

    results = service.validate_draft(alias)

    schema = next(result for result in results if result.stage == ValidationStage.SCHEMA)
    assert schema.passed is False
    assert schema.errors == ("removed_persona_alias",)


def test_binding_priority_and_surface_do_not_change_profile_id() -> None:
    bindings = tuple(
        PersonaBinding(
            binding_id=scope.value,
            scope=scope,
            scope_key=key,
            version_id="xiaohe_v1@1",
            surface=(("display_name", scope.value),),
        )
        for scope, key in (
            (BindingScope.GLOBAL, "*"),
            (BindingScope.PLATFORM, "qq"),
            (BindingScope.RELATIONSHIP, "admin_partner"),
            (BindingScope.PROFILE, "owner-profile"),
            (BindingScope.CONVERSATION, "conversation-1"),
        )
    )
    context = BindingContext(
        platform="qq",
        relationship="admin_partner",
        profile_id="owner-profile",
        conversation_id="conversation-1",
    )
    selected = resolve_binding(bindings, context)
    assert selected is not None
    assert selected.scope == BindingScope.CONVERSATION

    service = InMemoryPersonaManagementService()
    version = approved_version(service, draft_id="projection")
    projection = build_runtime_projection(version, selected)

    assert projection.profile_id == "xiaohe_v1"
    assert projection.surface == (("display_name", "conversation"),)
    assert SYSTEM_REQUIRED_GATES <= projection.effective_gates


def test_binding_falls_back_through_each_priority_level() -> None:
    bindings = (
        PersonaBinding("global", BindingScope.GLOBAL, "*", "xiaohe_v1@1"),
        PersonaBinding("platform", BindingScope.PLATFORM, "qq", "xiaohe_v1@2"),
        PersonaBinding("relationship", BindingScope.RELATIONSHIP, "normal_friend", "xiaohe_v1@3"),
    )

    assert resolve_binding(bindings, BindingContext(platform="qq")).binding_id == "platform"  # type: ignore[union-attr]
    assert (
        resolve_binding(bindings, BindingContext(platform="qq", relationship="normal_friend")).binding_id  # type: ignore[union-attr]
        == "relationship"
    )
    assert resolve_binding(bindings, BindingContext(platform="wechat")).binding_id == "global"  # type: ignore[union-attr]


def test_profile_version_audit_and_contract_immutability() -> None:
    service = InMemoryPersonaManagementService()
    first = approved_version(service, draft_id="audit-1")
    second = approved_version(service, draft_id="audit-2", style="新版本")

    assert [version.version_id for version in service.list_versions("xiaohe_v1")] == [
        "xiaohe_v1@1",
        "xiaohe_v1@2",
    ]
    assert first.source_draft_id == "audit-1"
    assert second.approved_by == "reviewer"
    with pytest.raises(FrozenInstanceError):
        second.version = 99  # type: ignore[misc]


def test_xiaohe_runtime_projection_preserves_stable_behavior_fields() -> None:
    service = InMemoryPersonaManagementService()
    version = approved_version(service, draft_id="equivalence")

    projection = build_runtime_projection(version)

    assert isinstance(projection, PersonaRuntimeProjection)
    assert projection.version_id == "xiaohe_v1@1"
    assert projection.default_style == "台湾国语、短句、自然亲近、有边界、不油腻"
    assert "稳定人格是小何" in projection.core_lines[0]
    assert "普通朋友面前保持友好边界" in projection.core_lines[1]
    assert not hasattr(projection, "draft_id")


def test_repository_state_survives_service_reconstruction() -> None:
    repository = InMemoryPersonaManagementRepository()
    first_service = InMemoryPersonaManagementService(repository)
    version = approved_version(first_service, draft_id="persistent")
    release = first_service.publish(version.version_id, actor_id="operator")

    reconstructed_service = InMemoryPersonaManagementService(repository)

    assert reconstructed_service.get_active_version("xiaohe_v1") == version
    assert reconstructed_service.list_releases("xiaohe_v1") == (release,)
    assert reconstructed_service.approve("persistent", actor_id="other-reviewer") == version


def test_binding_is_saved_through_repository_boundary() -> None:
    repository = InMemoryPersonaManagementRepository()
    service = InMemoryPersonaManagementService(repository)
    version = approved_version(service, draft_id="binding")
    service.publish(version.version_id, actor_id="operator")
    service.publish(version.version_id, actor_id="operator")
    binding = PersonaBinding(
        binding_id="qq-default",
        scope=BindingScope.PLATFORM,
        scope_key="qq",
        version_id=version.version_id,
    )

    assert service.save_binding(binding) == binding
    assert InMemoryPersonaManagementService(repository).list_bindings() == (binding,)

    missing = PersonaBinding(
        binding_id="missing",
        scope=BindingScope.GLOBAL,
        scope_key="*",
        version_id="xiaohe_v1@99",
    )
    with pytest.raises(PersonaManagementError, match="binding_version_not_found"):
        service.save_binding(missing)


def test_runtime_projection_rejects_binding_for_another_version() -> None:
    service = InMemoryPersonaManagementService()
    version_1 = approved_version(service, draft_id="projection-v1")
    version_2 = approved_version(service, draft_id="projection-v2", style="新版本")
    binding = PersonaBinding(
        binding_id="wrong-version",
        scope=BindingScope.GLOBAL,
        scope_key="*",
        version_id=version_2.version_id,
        surface=(("display_name", "新外壳"),),
    )

    with pytest.raises(ValueError, match="binding_version_mismatch"):
        build_runtime_projection(version_1, binding)


def test_rollback_rejects_version_that_has_never_been_released() -> None:
    service = InMemoryPersonaManagementService()
    version_1 = approved_version(service, draft_id="released")
    service.publish(version_1.version_id, actor_id="operator")
    version_2 = approved_version(service, draft_id="approved-only", style="未发布")

    with pytest.raises(PersonaManagementError, match="rollback_target_not_released"):
        service.rollback("xiaohe_v1", version_2.version_id, actor_id="operator")

    assert service.get_active_version("xiaohe_v1") == version_1


@pytest.mark.parametrize(
    ("binding", "error"),
    [
        (
            PersonaBinding("bad-global", BindingScope.GLOBAL, "qq", "xiaohe_v1@1"),
            "global_binding_key_must_be_wildcard",
        ),
        (
            PersonaBinding("empty-profile", BindingScope.PROFILE, " ", "xiaohe_v1@1"),
            "binding_scope_key_required",
        ),
        (
            PersonaBinding(
                "profile-override",
                BindingScope.GLOBAL,
                "*",
                "xiaohe_v1@1",
                surface=(("profile_id", "other-persona"),),
            ),
            "surface_cannot_override_profile_id",
        ),
    ],
)
def test_binding_rejects_invalid_scope_and_profile_override(binding, error: str) -> None:
    service = InMemoryPersonaManagementService()
    version = approved_version(service, draft_id="binding-validation")
    service.publish(version.version_id, actor_id="operator")

    with pytest.raises(PersonaManagementError, match=error):
        service.save_binding(binding)


def test_binding_rejects_unpublished_version_and_stale_binding_is_not_projected() -> None:
    service = InMemoryPersonaManagementService()
    version_1 = approved_version(service, draft_id="active-binding-1")
    binding = PersonaBinding(
        binding_id="qq",
        scope=BindingScope.PLATFORM,
        scope_key="qq",
        version_id=version_1.version_id,
        surface=(("display_name", "QQ 小何"),),
    )
    with pytest.raises(PersonaManagementError, match="binding_version_not_active"):
        service.save_binding(binding)

    service.publish(version_1.version_id, actor_id="operator")
    service.save_binding(binding)
    assert service.get_runtime_projection(
        "xiaohe_v1", BindingContext(platform="qq")
    ).surface == (("display_name", "QQ 小何"),)

    version_2 = approved_version(service, draft_id="active-binding-2", style="新版本")
    service.publish(version_2.version_id, actor_id="operator")
    projection = service.get_runtime_projection("xiaohe_v1", BindingContext(platform="qq"))
    assert projection.version_id == version_2.version_id
    assert projection.surface == ()


def test_status_reports_non_durable_memory_backend_and_safe_counts() -> None:
    service = InMemoryPersonaManagementService()
    empty = service.get_status()
    assert empty.storage_backend == "memory"
    assert empty.durable is False
    assert empty.write_ready is False
    assert empty.active_profiles == ()

    version = approved_version(service, draft_id="status")
    service.publish(version.version_id, actor_id="operator")
    service.save_binding(
        PersonaBinding(
            binding_id="global",
            scope=BindingScope.GLOBAL,
            scope_key="*",
            version_id=version.version_id,
        )
    )
    status = service.get_status()

    assert status.draft_count == 1
    assert status.version_count == 1
    assert status.release_count == 1
    assert status.binding_count == 1
    assert status.active_profiles == ("xiaohe_v1",)
