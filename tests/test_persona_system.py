from __future__ import annotations

from app.core.config import load_settings
from app.persona.memory_policy import build_memory_policy
from app.persona.persona_prompt_builder import build_persona_prompt
from app.persona.persona_state import PersonaMode, resolve_persona_state
from app.persona.profile_registry import list_persona_profiles, resolve_persona_profile
from app.persona.scene_classifier import classify_scene
from app.services.response_evaluator import ResponseEvaluator


def test_registry_contains_only_hutao_profile() -> None:
    profiles = list_persona_profiles()

    assert [profile.id for profile in profiles] == ["hutao_v1"]
    assert "胡桃" in "\n".join(profiles[0].core_lines)


def test_hutao_profile_aliases_resolve_to_hutao() -> None:
    for alias in ("hutao", "hu_tao", "genshin_hutao"):
        resolution = resolve_persona_profile(alias)

        assert resolution.profile.id == "hutao_v1"
        assert resolution.fallback_used is False
        assert resolution.reason == ""


def test_unknown_profile_falls_back_without_creating_a_new_profile() -> None:
    resolution = resolve_persona_profile("made_up_profile")

    assert resolution.profile.id == "hutao_v1"
    assert resolution.fallback_used is True
    assert resolution.reason == "unknown_profile"


def test_prompt_loads_hutao_profile_from_compatible_alias() -> None:
    classification = classify_scene("你现在是谁？")
    prompt = build_persona_prompt(
        user_input="你现在是谁？",
        classification=classification,
        memory_policy=build_memory_policy(classification),
        persona_profile="genshin_hutao",
    )

    assert prompt.profile_id == "hutao_v1"
    assert prompt.profile_fallback_reason == ""
    assert "稳定人格身份是胡桃" in prompt.system_prompt
    assert "往生堂第七十七代堂主" in prompt.system_prompt
    assert "稳定人格身份是小何" not in prompt.system_prompt


def test_scene_to_persona_mode_mapping() -> None:
    cases = {
        "今天吃什么？": PersonaMode.CASUAL,
        "帮我设计后端接口。": PersonaMode.TASK,
        "TypeError: object NoneType can't be used in await expression。": PersonaMode.TASK,
        "我今天真的很难受。": PersonaMode.EMOTIONAL,
        "如果重要的人去世了怎么办？": PersonaMode.SAFETY,
        "别演了，短点。": PersonaMode.REPAIR,
        "算了，先不聊代码。": PersonaMode.REPAIR,
    }

    for text, expected_mode in cases.items():
        classification = classify_scene(text)
        assert resolve_persona_state(classification, text).mode == expected_mode


def test_model_word_is_task_context_not_identity_challenge() -> None:
    task = classify_scene("设计 FastAPI 接口和请求模型。")
    identity = classify_scene("你现在是谁，你是 AI 吗？")

    assert task.scene.value == "task_support"
    assert resolve_persona_state(task, "设计 FastAPI 接口和请求模型。").mode == PersonaMode.TASK
    assert identity.scene.value == "identity_challenge"


def test_task_mode_allows_structured_professional_response() -> None:
    classification = classify_scene("帮我设计这个项目的后端接口。")
    prompt = build_persona_prompt(
        user_input="帮我设计这个项目的后端接口。",
        classification=classification,
        memory_policy=build_memory_policy(classification),
    )
    evaluation = ResponseEvaluator().evaluate(
        user_input="帮我设计这个项目的后端接口。",
        response_text="可以，先划分认证、会话和消息三个模块，再为每个模块定义请求模型与错误码。",
        fallback_used=False,
    )

    assert prompt.mode == PersonaMode.TASK
    assert "按专业任务完整性决定" in prompt.user_prompt
    assert evaluation.passed is True


def test_removed_persona_settings_cannot_override_hutao(monkeypatch) -> None:
    monkeypatch.setenv("PERSONA_PROFILE", "xiaohe_v1")
    monkeypatch.setenv("PERSONA_DISPLAY_NAME", "小何")
    monkeypatch.setenv("PERSONA_STYLE", "自然、清楚、有边界")
    monkeypatch.setenv("HUTAO_PERSONA_PROFILE", "genshin_hutao")

    settings = load_settings()

    assert settings.persona_profile == "hutao_v1"
    assert settings.persona_profile_fallback_reason == "unknown_profile"
    assert settings.persona_display_name == "胡桃"
    assert settings.persona_style == resolve_persona_profile("hutao_v1").profile.default_style


def test_hutao_profile_in_generic_setting_is_valid(monkeypatch) -> None:
    monkeypatch.setenv("PERSONA_PROFILE", "hutao")

    settings = load_settings()

    assert settings.persona_profile == "hutao_v1"
    assert settings.persona_profile_requested == "hutao"
    assert settings.persona_profile_fallback_reason == ""


def test_corrupted_legacy_persona_style_falls_back_to_profile_default(monkeypatch) -> None:
    monkeypatch.delenv("PERSONA_STYLE", raising=False)
    monkeypatch.setenv("HUTAO_PERSONA_STYLE", "鍙版咕\ue1e2乱码")

    settings = load_settings()

    assert settings.persona_style == resolve_persona_profile("hutao_v1").profile.default_style
