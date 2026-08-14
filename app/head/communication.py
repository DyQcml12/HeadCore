from __future__ import annotations

from app.head.contracts import (
    CommunicationAct,
    CommunicationState,
    LatentIntentHypothesis,
    TurnTakingPolicy,
)
from app.mind.conversation_state import ConversationState


LOW_INFORMATION = {"嗯", "嗯嗯", "哦", "噢", "唉", "然后呢", "继续说", "你说"}
NO_ADVICE_MARKERS = ("不想听大道理", "别讲道理", "别建议", "不用建议", "别说教", "听我说")
ADVICE_MARKERS = ("怎么办", "怎么做", "给点建议", "帮我想", "该不该", "如何")
WITHDRAWAL_MARKERS = ("算了", "当我没说", "不说了", "没事了")
CORRECTION_MARKERS = ("不是这个意思", "你理解错了", "我说的是", "别演", "别这么说")


def build_communication_state(
    *,
    user_input: str,
    conversation: ConversationState,
    has_active_task: bool,
) -> CommunicationState:
    text = user_input.strip()
    acts: list[CommunicationAct] = []
    constraints: list[str] = []
    hypotheses: list[LatentIntentHypothesis] = []

    if any(marker in text for marker in CORRECTION_MARKERS) or conversation.last_user_correction != "none":
        acts.append(CommunicationAct.ACCEPT_CORRECTION)
        constraints.extend(("acknowledge_correction", "avoid_defensiveness"))
    if conversation.recent_user_mood in {"vulnerable", "tired"}:
        acts.append(CommunicationAct.EMOTIONAL_SUPPORT)
    if any(marker in text for marker in NO_ADVICE_MARKERS):
        acts.extend((CommunicationAct.EMOTIONAL_SUPPORT, CommunicationAct.AVOID_ADVICE))
        constraints.extend(("no_advice", "no_moralizing"))
    elif any(marker in text for marker in ADVICE_MARKERS):
        acts.append(CommunicationAct.REQUEST_ADVICE)

    if any(marker in text for marker in WITHDRAWAL_MARKERS):
        acts.append(CommunicationAct.TOPIC_WITHDRAWAL)
        hypotheses.append(
            LatentIntentHypothesis(
                kind="possible_disappointment_or_withdrawal",
                confidence=0.45,
                evidence=_compact(text),
            )
        )
        constraints.append("do_not_assume_emotion")
    if has_active_task:
        acts.append(CommunicationAct.CONTINUE_TASK)
    if text in LOW_INFORMATION:
        acts.append(CommunicationAct.ACKNOWLEDGE)
    if not acts:
        acts.append(CommunicationAct.ANSWER_QUESTION)

    acts = _deduplicate(acts)
    primary = _primary_act(acts)
    return CommunicationState(
        primary_act=primary,
        secondary_acts=tuple(act for act in acts if act != primary),
        hypotheses=tuple(hypotheses),
        turn_policy=_build_turn_policy(
            text=text,
            conversation=conversation,
            acts=acts,
            constraints=tuple(dict.fromkeys(constraints)),
        ),
    )


def _primary_act(acts: list[CommunicationAct]) -> CommunicationAct:
    priority = (
        CommunicationAct.ACCEPT_CORRECTION,
        CommunicationAct.EMOTIONAL_SUPPORT,
        CommunicationAct.TOPIC_WITHDRAWAL,
        CommunicationAct.REQUEST_ADVICE,
        CommunicationAct.CONTINUE_TASK,
        CommunicationAct.ACKNOWLEDGE,
        CommunicationAct.ANSWER_QUESTION,
    )
    return next(act for act in priority if act in acts)


def _build_turn_policy(
    *,
    text: str,
    conversation: ConversationState,
    acts: list[CommunicationAct],
    constraints: tuple[str, ...],
) -> TurnTakingPolicy:
    low_information = text in LOW_INFORMATION
    emotional = CommunicationAct.EMOTIONAL_SUPPORT in acts
    withdrawal = CommunicationAct.TOPIC_WITHDRAWAL in acts
    technical = conversation.current_topic == "technical_or_project"
    response_length = "very_short" if low_information or withdrawal else "short" if emotional else "task_scaled"
    initiative = "listen" if emotional or withdrawal or low_information else "solve" if technical else "respond"
    question_budget = 1 if withdrawal else 0 if low_information or CommunicationAct.AVOID_ADVICE in acts else 1
    advice_budget = 0 if CommunicationAct.AVOID_ADVICE in acts or withdrawal else 2 if technical else 1
    persona_intensity = 0.15 if emotional or withdrawal else 0.25 if technical else 0.35
    return TurnTakingPolicy(
        response_length=response_length,
        initiative=initiative,
        question_budget=question_budget,
        advice_budget=advice_budget,
        persona_intensity=persona_intensity,
        constraints=constraints,
    )


def _deduplicate(values: list[CommunicationAct]) -> list[CommunicationAct]:
    return list(dict.fromkeys(values))


def _compact(text: str, limit: int = 48) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"
