from __future__ import annotations

from app.dialogue.expression_policy import (
    evaluate_sticker_decision,
    evaluate_voice_decision,
    sticker_expression_threshold,
    voice_expression_threshold,
)
from app.dialogue.policy import build_dialogue_decision, constrain_reply_text
from app.dialogue.types import ExpressionSettings, ExpressionState


def test_dialogue_policy_classifies_short_chat_and_task_context() -> None:
    short_decision = build_dialogue_decision("干嘛呢", channel="qq")
    task_decision = build_dialogue_decision("帮我写一个完整方案", channel="qq")

    assert short_decision.dialogue_act == "affection"
    assert short_decision.response_mode == "short_chat"
    assert short_decision.prompt_instruction is not None
    assert task_decision.response_mode == "task_answer"
    assert task_decision.prompt_instruction is None


def test_dialogue_policy_constrains_only_chatty_replies() -> None:
    long_reply = "我在整理一堆客户名单呢，里面怪事儿不少，看完保管你来精神。顺手还翻出几条旧记录。"

    assert len(constrain_reply_text(long_reply, user_input="干嘛呢", max_chars=35, channel="qq")) <= 35
    assert constrain_reply_text(long_reply, user_input="帮我写一个完整方案", max_chars=35, channel="qq") == long_reply


def test_core_expression_policy_scores_sticker_intent_and_blocks_technical_context() -> None:
    settings = ExpressionSettings(
        sticker_auto_reply_enabled=True,
        sticker_auto_probability=1.0,
        sticker_cooldown_messages=1,
        sticker_cooldown_seconds=1.0,
    )
    state = ExpressionState(sticker_turns_since=5, last_sticker_at=0)

    decision = evaluate_sticker_decision(
        settings=settings,
        user_input="哈哈这个太好玩了",
        reply_text="本堂主也觉得有点意思。",
        state=state,
        now=100,
    )
    blocked = evaluate_sticker_decision(
        settings=settings,
        user_input="代码报错了",
        reply_text="把报错第一行给我。",
        state=state,
        now=100,
    )

    assert decision.should_send is True
    assert decision.intent == "celebrate"
    assert blocked.should_send is False
    assert "technical_context" in blocked.reasons


def test_core_expression_policy_uses_semantic_need_without_high_probability() -> None:
    settings = ExpressionSettings(
        sticker_auto_reply_enabled=True,
        sticker_auto_probability=0.18,
        sticker_cooldown_messages=3,
        sticker_cooldown_seconds=30.0,
    )
    state = ExpressionState(sticker_turns_since=9, last_sticker_at=0)

    support = evaluate_sticker_decision(
        settings=settings,
        user_input="抱抱我，有点难过",
        reply_text="过来，本堂主陪你坐一会儿。",
        state=state,
        now=100,
    )
    casual = evaluate_sticker_decision(
        settings=settings,
        user_input="干嘛呢",
        reply_text="我在翻旧账，正好等你。",
        state=state,
        now=100,
    )
    low_ack = evaluate_sticker_decision(
        settings=settings,
        user_input="嗯",
        reply_text="我在。",
        state=state,
        now=100,
    )

    assert support.should_send is True
    assert support.intent == "support"
    assert "intent:support" in support.reasons
    assert casual.should_send is True
    assert casual.intent == "cute_react"
    assert low_ack.should_send is False
    assert low_ack.reasons == ["low_expression_ack"]


def test_core_expression_policy_probability_only_adjusts_sensitivity() -> None:
    assert sticker_expression_threshold(0.0) == 0.56
    assert sticker_expression_threshold(1.0) == 0.4
    assert sticker_expression_threshold(99.0) == 0.4
    assert sticker_expression_threshold(-1.0) == 0.56


def test_core_expression_policy_voice_defaults_to_disabled() -> None:
    decision = evaluate_voice_decision(
        settings=ExpressionSettings(voice_auto_reply_enabled=False),
        user_input="你在吗，陪我说说话",
        state=ExpressionState(voice_turns_since=99, last_voice_at=0),
        now=1000,
    )

    assert decision.should_send is False
    assert decision.reasons == ["disabled"]


def test_core_expression_policy_voice_uses_semantic_need_when_enabled() -> None:
    settings = ExpressionSettings(
        voice_auto_reply_enabled=True,
        voice_auto_probability=0.08,
        voice_cooldown_messages=4,
        voice_cooldown_seconds=30.0,
    )
    state = ExpressionState(voice_turns_since=12, last_voice_at=0)

    comfort = evaluate_voice_decision(
        settings=settings,
        user_input="有点累，陪我说说话",
        state=state,
        now=100,
    )
    technical = evaluate_voice_decision(
        settings=settings,
        user_input="语音模型训练报错了",
        state=state,
        now=100,
    )
    low_ack = evaluate_voice_decision(
        settings=settings,
        user_input="嗯",
        state=state,
        now=100,
    )

    assert comfort.should_send is True
    assert comfort.style == "comfort"
    assert "companion_intent" in comfort.reasons
    assert "emotion:comfort" in comfort.reasons
    assert technical.should_send is False
    assert "technical_context" in technical.reasons
    assert low_ack.should_send is False
    assert low_ack.reasons == ["low_expression_ack"]


def test_core_expression_policy_voice_probability_only_adjusts_sensitivity() -> None:
    assert voice_expression_threshold(0.0) == 0.64
    assert voice_expression_threshold(1.0) == 0.5
    assert voice_expression_threshold(99.0) == 0.5
    assert voice_expression_threshold(-1.0) == 0.64
