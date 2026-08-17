from __future__ import annotations

from app.services.chat_service import _camera_context_block


class FakeCameraProvider:
    def __init__(self, context: str = "") -> None:
        self.context = context

    def latest_context(self) -> str:
        return self.context


def test_camera_block_injects_confirmed_labels_for_visual_question() -> None:
    provider = FakeCameraProvider(
        "scene: desk | objects: keyboard, laptop | pose: sitting | gesture: typing"
    )

    block = _camera_context_block(provider, user_input="我眼前有什么？", relationship_role="normal")

    assert "keyboard" in block
    assert "不得据此推断情绪、身份或意图" in block


def test_camera_block_answers_label_question_without_explicit_visual_marker() -> None:
    provider = FakeCameraProvider("objects: cup | scene: desk")

    block = _camera_context_block(provider, user_input="桌上有没有杯子？", relationship_role="normal")

    assert "cup" in block


def test_camera_block_is_empty_for_irrelevant_turn() -> None:
    provider = FakeCameraProvider("scene: desk | objects: keyboard")

    block = _camera_context_block(provider, user_input="给我讲个笑话", relationship_role="normal")

    assert block == ""


def test_camera_block_gives_clarification_when_no_context_but_visual_question() -> None:
    provider = FakeCameraProvider("")

    block = _camera_context_block(provider, user_input="我刚才发生了什么？", relationship_role="normal")

    assert "没有看清" in block


def test_camera_block_is_empty_without_provider() -> None:
    assert _camera_context_block(None, user_input="我眼前有什么？", relationship_role="normal") == ""


def test_camera_block_is_empty_for_blocked_relationship() -> None:
    provider = FakeCameraProvider("scene: desk | objects: keyboard")

    block = _camera_context_block(provider, user_input="我眼前有什么？", relationship_role="blocked")

    assert block == ""
