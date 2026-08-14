from __future__ import annotations

from app.head.contracts import CommunicationAct, CommunicationState, HeadAction, HeadDecision
from app.mind.conversation_state import ConversationState
from app.mind.social_state import SocialState


def decide_head_action(
    *,
    user_input: str,
    relationship_role: str,
    conversation: ConversationState,
    social: SocialState,
    active_task: str,
    uncertainties: tuple[str, ...],
    communication: CommunicationState,
) -> HeadDecision:
    if relationship_role == "blocked":
        return HeadDecision(HeadAction.REFUSE, "relationship_blocked", "拒绝进入对话")
    if CommunicationAct.ACCEPT_CORRECTION in _all_acts(communication):
        return HeadDecision(HeadAction.REPAIR, "conversation_repair", "先体现纠正并恢复自然交流")
    if CommunicationAct.TOPIC_WITHDRAWAL in _all_acts(communication):
        return HeadDecision(
            HeadAction.SUPPORT,
            "ambiguous_topic_withdrawal",
            "尊重停止表达，用一句轻确认留出空间；不要断言用户情绪",
        )
    if CommunicationAct.EMOTIONAL_SUPPORT in _all_acts(communication):
        objective = "先回应感受并陪伴，不提供建议" if communication.turn_policy.advice_budget == 0 else "先回应感受，再决定是否追问"
        return HeadDecision(HeadAction.SUPPORT, "support_need", objective)
    if social.boundary_mode == "repairing":
        return HeadDecision(HeadAction.REPAIR, "conversation_repair", "先降低语气强度并恢复自然交流")
    if any(item.startswith("world_input_required:") for item in uncertainties):
        return HeadDecision(
            HeadAction.CLARIFY,
            "world_requires_input",
            "先补齐世界工具完成当前请求所需的信息，不猜测位置、时间或对象",
        )
    if any(item.startswith("world_evidence_unavailable:") for item in uncertainties):
        return HeadDecision(
            HeadAction.ANSWER,
            "world_evidence_unavailable",
            "明确说明实时来源不可用，不把模型常识伪装成当前事实",
        )
    if any(item.startswith("world_evidence_uncertain:") for item in uncertainties):
        return HeadDecision(
            HeadAction.ANSWER,
            "world_evidence_uncertain",
            "保留证据冲突或过期状态，不把任一外部结果说成确定事实",
        )
    if _needs_clarification(user_input, uncertainties):
        return HeadDecision(HeadAction.CLARIFY, "missing_required_context", "只追问完成当前请求所需的信息")
    if active_task != "none":
        return HeadDecision(HeadAction.CONTINUE_TASK, "active_task", "承接当前任务并推进一个明确步骤")
    return HeadDecision(HeadAction.ANSWER, "direct_response", "直接回应用户当前意图")


def _all_acts(communication: CommunicationState) -> tuple[CommunicationAct, ...]:
    return (communication.primary_act, *communication.secondary_acts)


def _needs_clarification(user_input: str, uncertainties: tuple[str, ...]) -> bool:
    if not uncertainties:
        return False
    normalized = user_input.strip().lower()
    request_markers = ("怎么", "如何", "帮我", "能不能", "为什么", "报错", "计划", "设计")
    vague_references = ("这个", "那个", "它", "这样", "那样")
    return any(marker in normalized for marker in request_markers) and (
        len(normalized) <= 12 or any(marker in normalized for marker in vague_references)
    )
