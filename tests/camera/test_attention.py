from app.camera.attention import camera_clarification_instruction, select_camera_context


CONTEXT = "book | phone | sitting ; changes: appeared:objects:phone"


def test_explicit_visual_question_keeps_current_context() -> None:
    selection = select_camera_context("你看到画面里有什么？", CONTEXT)

    assert selection.text == CONTEXT
    assert selection.reason == "explicit_visual_request"


def test_related_question_keeps_only_matching_label() -> None:
    selection = select_camera_context("你看到手机了吗？", CONTEXT)

    assert selection.text == "phone ; changes: appeared:objects:phone"
    assert selection.reason == "label_match"


def test_change_question_keeps_only_change_context() -> None:
    selection = select_camera_context("刚刚发生什么变化？", CONTEXT)

    assert selection.text == "appeared:objects:phone"
    assert selection.reason == "change_request"


def test_ordinary_chat_does_not_receive_camera_context() -> None:
    selection = select_camera_context("今天心情不错。", CONTEXT)

    assert selection.text == ""
    assert selection.reason == "irrelevant"


def test_visual_question_without_context_requests_headcore_clarification() -> None:
    selection = select_camera_context("你看到画面里有什么？", "")

    assert selection.text == ""
    assert selection.needs_clarification is True
    assert "不要猜测" in camera_clarification_instruction()


def test_unmatched_label_question_requests_clarification_without_claiming_absence() -> None:
    selection = select_camera_context("你看到猫了吗？", CONTEXT)

    assert selection.text == ""
    assert selection.reason == "label_context_unavailable"
    assert selection.needs_clarification is True
