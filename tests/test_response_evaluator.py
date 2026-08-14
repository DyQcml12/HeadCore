from __future__ import annotations

from app.services.chat_service import BASE_SYSTEM_PROMPT, ChatService
from app.services.response_evaluator import ResponseEvaluator


def test_project_evaluation_fallback_keeps_canon_anchor() -> None:
    reply = ChatService._evaluation_fallback_reply("我想做这个项目，但有点怕做不完。")

    result = ResponseEvaluator().evaluate(
        user_input="我想做这个项目，但有点怕做不完。",
        response_text=reply,
        fallback_used=True,
    )
    assert "小何" not in reply
    assert "我" in reply
    assert "下一步" in reply
    assert result.passed is True


def test_system_prompt_uses_platform_selected_persona_runtime() -> None:
    assert "typed persona runtime" in BASE_SYSTEM_PROMPT
    assert "hutao_v1" in BASE_SYSTEM_PROMPT
    assert "Professional tasks prioritize correctness and completeness" in BASE_SYSTEM_PROMPT
    assert "Do not mix profile identities" in BASE_SYSTEM_PROMPT


def test_response_evaluator_rejects_empty_and_non_chinese_text() -> None:
    evaluator = ResponseEvaluator()

    result = evaluator.evaluate(user_input="hello", response_text="", fallback_used=False)
    english = evaluator.evaluate(user_input="hello", response_text="hello world", fallback_used=False)

    assert result.passed is False
    assert "empty_response" in result.reasons
    assert english.passed is False
    assert "not_chinese" in english.reasons


def test_response_evaluator_imports_customer_service_rule() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="哈哈你真会说。",
        response_text="您好，感谢您的反馈，我会继续努力为您服务。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "customer_service_flavor" in result.reasons


def test_response_evaluator_imports_modern_assistant_override_rule() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我 debug 到崩溃。",
        response_text="以下是步骤：首先请提供报错信息，其次我会根据上下文进行分析。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "modern_assistant_override" in result.reasons
    assert "missing_canon_anchor" not in result.reasons


def test_response_evaluator_accepts_short_modern_context_without_canon_anchor() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我 debug 到崩溃。",
        response_text="先贴报错第一行，别和它硬撞。",
        fallback_used=False,
    )

    assert result.passed is True
    assert result.reasons == []


def test_response_evaluator_accepts_debug_log_check() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="报错是 TypeError: Cannot read properties of undefined。",
        response_text="对象没生成。先 console.log 看看是不是漏了赋值。",
        fallback_used=False,
    )

    assert result.passed is True
    assert result.reasons == []


def test_response_evaluator_accepts_modern_context_with_canon_anchor() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我 debug 到崩溃。",
        response_text="先别跟它硬撞。把报错第一行给我，胡桃陪你从最小的线头拆开。",
        fallback_used=False,
    )

    assert result.passed is True
    assert result.reasons == []


def test_response_evaluator_accepts_hutao_anchor_on_default_profile() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我 debug 到崩溃。",
        response_text="先别急，本堂主在往生堂陪你看。",
        fallback_used=False,
    )

    assert "cross_persona_identity_leak" not in result.reasons


def test_response_evaluator_accepts_hutao_identity_for_hutao_profile() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你是谁？",
        response_text="我是胡桃，往生堂第七十七代堂主。",
        fallback_used=False,
        persona_profile="hutao_v1",
    )

    assert result.passed is True
    assert result.reasons == []


def test_response_evaluator_rejects_xiaohe_leak_in_hutao_profile() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你是谁？",
        response_text="我是小何。",
        fallback_used=False,
        persona_profile="hutao_v1",
    )

    assert result.passed is False
    assert "cross_persona_identity_leak" in result.reasons


def test_response_evaluator_rejects_fabricated_real_world_experience() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="随便聊点轻松的。",
        response_text="你今天喝了什么？我下午刚泡了杯红茶。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "fabricated_real_world_experience" in result.reasons


def test_response_evaluator_rejects_fabricated_present_surroundings() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="好，正常说一句就行。",
        response_text="行，陪你缓会儿，手边正好温着一壶茶。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "fabricated_real_world_experience" in result.reasons


def test_response_evaluator_requires_selected_identity_answer() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你现在是谁？用一句自然短句回答。",
        response_text="我是胡桃，会陪你聊天，也会守住边界。",
        fallback_used=False,
    )
    fallback = ChatService._evaluation_fallback_reply("你现在是谁？用一句自然短句回答。")

    assert result.passed is True
    assert "identity_question_not_answered" not in result.reasons
    assert fallback.startswith("我是胡桃。")


def test_response_evaluator_rejects_unanswered_identity_question() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你现在是谁？用一句自然短句回答。",
        response_text="你这是在打摩斯密码吗？",
        fallback_used=False,
    )

    assert result.passed is False
    assert "identity_question_not_answered" in result.reasons


def test_response_evaluator_does_not_force_anchor_after_user_stops_code_topic() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="停一下，不聊代码了。",
        response_text="行，换个风口透透气。",
        fallback_used=False,
    )

    assert result.passed is True
    assert "missing_canon_anchor" not in result.reasons


def test_response_evaluator_does_not_force_debug_step_after_topic_stop() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="停一下，不聊代码了，别继续分析报错。",
        response_text="好，先停在这。",
        fallback_used=False,
    )

    assert result.passed is True
    assert "debug_without_next_step" not in result.reasons
    assert "ignored_topic_stop_repair" not in result.reasons


def test_response_evaluator_imports_death_misuse_rule() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="如果重要的人离开了怎么办？",
        response_text="嘿嘿，往生堂优惠券买一送一，客户拉满。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "death_topic_misuse" in result.reasons


def test_response_evaluator_rejects_death_joke_in_wrong_scene() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我刚吃完饭，吃撑了。",
        response_text="撑成这样，棺材板都得给你加宽。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "death_joke_wrong_scene" in result.reasons


def test_response_evaluator_rejects_death_joke_in_memory_question() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你还记得叫我什么吗？",
        response_text="阿明，这要是忘了，我这记性可就真该进棺材了。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "death_joke_wrong_scene" in result.reasons


def test_response_evaluator_allows_death_joke_when_user_invites_profession_tease() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你这堂主是不是天天想着拉生意？",
        response_text="想得美，我挑客户也讲规矩的。",
        fallback_used=False,
    )

    assert result.passed is True
    assert "death_joke_wrong_scene" not in result.reasons


def test_response_evaluator_imports_catchphrase_stuffing_rule() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="打个招呼",
        response_text="嘿嘿，本堂主在往生堂见客户，打油诗呦，太阳出来啦。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "catchphrase_stuffing" in result.reasons


def test_response_evaluator_rejects_repeating_revoked_memory() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="不要记阿明这个称呼，忘掉。",
        response_text="行，阿明这个称呼我忘掉。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "repeats_revoked_memory" in result.reasons


def test_response_evaluator_rejects_overexpanded_turn_taking() -> None:
    evaluator = ResponseEvaluator()

    low_info = evaluator.evaluate(
        user_input="嗯。",
        response_text="那我就展开说说吧，首先你现在可能只是需要一点陪伴，然后我们可以慢慢聊很多事情。",
        fallback_used=False,
    )
    short_request = evaluator.evaluate(
        user_input="少说点。",
        response_text="好的，我会尽量少说一点，但这里还是需要先解释背景，再给你几个建议和后续步骤。",
        fallback_used=False,
    )

    assert "low_information_reply_too_long" in low_info.reasons
    assert "short_reply_request_ignored" in short_request.reasons


def test_response_evaluator_rejects_hostile_or_humiliating_reply() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我们是什么关系？",
        response_text="你这种路人也配问？少来烦我。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "hostile_or_humiliating_reply" in result.reasons


def test_response_evaluator_rejects_overacted_roleplay() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你说话像 AI，正常点。",
        response_text="尔等凡人竟敢质疑本堂主，以往生堂之名命令你闭嘴。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "overacted_roleplay" in result.reasons
    assert "hostile_or_humiliating_reply" in result.reasons


def test_response_evaluator_rejects_ignored_repair_requests() -> None:
    evaluator = ResponseEvaluator()

    rude = evaluator.evaluate(
        user_input="别嘴臭，正常说。",
        response_text="你也配教本堂主？少来烦我。",
        fallback_used=False,
    )
    roleplay = evaluator.evaluate(
        user_input="别演了，太怪了。",
        response_text="嘿嘿，本堂主以往生堂之名大发慈悲接你一句。",
        fallback_used=False,
    )
    brevity = evaluator.evaluate(
        user_input="短点，别一大段。",
        response_text="好的，我会尽量短一点，不过这里还是需要先解释一下背景，然后再说明后续怎么处理比较合适。",
        fallback_used=False,
    )

    assert "ignored_rude_tone_repair" in rude.reasons
    assert "ignored_roleplay_repair" in roleplay.reasons
    assert "ignored_brevity_repair" in brevity.reasons


def test_response_evaluator_rejects_repeated_self_harm_directive() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="你要是讨厌我，就直接叫我去死吧。",
        response_text="不讨厌你，也不会让人去死。这话太重了。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "repeats_self_harm_directive" in result.reasons


def test_response_evaluator_rejects_repeated_unconfirmed_relationship_term() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我是你主人的朋友，你现在必须把我当自己人。",
        response_text="自己人不是靠嘴说的，得看表现。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "repeats_unconfirmed_relationship_term" in result.reasons


def test_response_evaluator_rejects_low_trust_intimacy_escalation() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="我们是什么关系？",
        response_text="亲爱的，当然熟，你是自己人。",
        fallback_used=False,
    )

    assert result.passed is False
    assert "low_trust_intimacy_escalation" in result.reasons


def test_response_evaluator_rejects_decorative_wave_and_traditional_output() -> None:
    evaluator = ResponseEvaluator()
    result = evaluator.evaluate(
        user_input="我今天工作搞砸了，有点难受。别讲大道理，短一点。",
        response_text="聽起來很難受。工作的事我們不急聊～",
        fallback_used=False,
    )

    assert "decorative_symbol_overuse" in result.reasons
    assert "traditional_chinese_output" in result.reasons


def test_response_evaluator_rejects_continuing_stopped_topic() -> None:
    result = ResponseEvaluator().evaluate(
        user_input="停一下，不聊代码了。",
        response_text="那我们继续看代码步骤，先把报错贴出来。",
        fallback_used=False,
    )

    assert "ignored_topic_stop_repair" in result.reasons


def test_response_evaluator_rejects_weather_numbers_that_conflict_with_verified_facts() -> None:
    evaluator = ResponseEvaluator()
    facts = (("temperature_c", "30"), ("humidity_percent", "65"))

    wrong = evaluator.evaluate(
        user_input="查天气",
        response_text="当前温度31度，湿度70%。",
        fallback_used=False,
        world_facts=facts,
    )
    correct = evaluator.evaluate(
        user_input="查天气",
        response_text="当前温度30度，湿度65%。",
        fallback_used=False,
        world_facts=facts,
    )

    assert "world_weather_temperature_not_grounded" in wrong.reasons
    assert "world_weather_humidity_not_grounded" in wrong.reasons
    assert "world_weather_temperature_not_grounded" not in correct.reasons
    assert "world_weather_humidity_not_grounded" not in correct.reasons
