from __future__ import annotations

from dataclasses import dataclass


_VISUAL_REQUEST_MARKERS = ("画面", "视频", "镜头", "摄像", "眼前", "看见什么", "看到什么", "有什么")
_CHANGE_REQUEST_MARKERS = ("刚刚", "发生", "变化", "怎么了", "出现", "不见", "消失")
_LABEL_KEYWORDS = {
    "backpack": ("背包",),
    "book": ("书", "阅读"),
    "bottle": ("瓶", "水", "喝"),
    "car": ("车",),
    "cat": ("猫",),
    "chair": ("椅",),
    "cup": ("杯", "喝"),
    "desk": ("桌",),
    "dog": ("狗",),
    "keyboard": ("键盘",),
    "laptop": ("电脑",),
    "mouse": ("鼠标",),
    "person": ("人",),
    "phone": ("手机", "电话"),
    "screen": ("屏幕",),
    "table": ("桌",),
    "standing": ("站",),
    "sitting": ("坐",),
    "walking": ("走",),
    "leaning": ("靠",),
    "head_down": ("低头",),
    "pointing": ("指",),
    "raised_hand": ("举手",),
    "waving": ("挥手",),
    "writing": ("写",),
    "typing": ("打字",),
}


@dataclass(frozen=True)
class CameraAttentionSelection:
    text: str
    reason: str
    needs_clarification: bool = False


def select_camera_context(user_input: str, context: str) -> CameraAttentionSelection:
    """Select only visual labels that are relevant to the current private turn."""
    question = user_input.strip().lower()
    current, changes = _split_context(context)
    if not question:
        return CameraAttentionSelection("", "empty")
    explicit_request = any(marker in question for marker in _VISUAL_REQUEST_MARKERS)
    change_request = any(marker in question for marker in _CHANGE_REQUEST_MARKERS)
    if not current:
        if explicit_request or change_request or _is_label_question(question):
            return CameraAttentionSelection("", "visual_context_unavailable", True)
        return CameraAttentionSelection("", "empty")
    if explicit_request:
        return CameraAttentionSelection(context.strip()[:240], "explicit_visual_request")
    if changes and change_request:
        return CameraAttentionSelection(changes[:240], "change_request")
    if change_request:
        return CameraAttentionSelection("", "change_context_unavailable", True)

    matched = [label for label in current.split(" | ") if _matches(label, question)]
    if not matched:
        if _is_label_question(question):
            return CameraAttentionSelection("", "label_context_unavailable", True)
        return CameraAttentionSelection("", "irrelevant")
    matching_changes = [change for change in changes.split(" | ") if _matches(change, question)]
    text = " | ".join(dict.fromkeys(matched))
    if matching_changes:
        text += " ; changes: " + " | ".join(dict.fromkeys(matching_changes))
    return CameraAttentionSelection(text[:240], "label_match")


def camera_clarification_instruction() -> str:
    return (
        "[当前视觉线索不足以回答用户关于画面的问题。不要猜测或断言；"
        "请用自然口吻说明这边没有看清，并请用户描述、调整画面或稍后再问。]"
    )


def _split_context(context: str) -> tuple[str, str]:
    current, marker, changes = context.strip().partition(" ; changes: ")
    return current, changes if marker else ""


def _matches(label: str, question: str) -> bool:
    normalized = label.lower()
    for machine_label, keywords in _LABEL_KEYWORDS.items():
        if machine_label in normalized and any(keyword in question for keyword in keywords):
            return True
    return False


def _is_label_question(question: str) -> bool:
    has_label_keyword = any(
        keyword in question for keywords in _LABEL_KEYWORDS.values() for keyword in keywords
    )
    has_question_signal = any(marker in question for marker in ("吗", "？", "?", "在哪", "有没有", "是否", "看见", "看到"))
    return has_label_keyword and has_question_signal
