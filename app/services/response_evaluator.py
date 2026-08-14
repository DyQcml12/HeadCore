from __future__ import annotations

import re
from dataclasses import dataclass

from app.dialogue.repair_policy import build_repair_policy
from app.persona.memory_service import extract_memory_terms
from app.persona.profile_registry import resolve_persona_profile
from app.persona.turn_taking import classify_turn_taking
from app.persona.response_rules import (
    AI_IDENTITY_MARKERS,
    CATCHPHRASE_MARKERS,
    CUSTOMER_SERVICE_MARKERS,
    DEATH_JOKE_MARKERS,
    DEATH_MISUSE_MARKERS,
    EMOTIONAL_SUPPORT_CONTEXT_MARKERS,
    GENERIC_ADVICE_MARKERS,
    LIFE_DEATH_CONTEXT_MARKERS,
    MODERN_ASSISTANT_MARKERS,
    MODERN_CONTEXT_MARKERS,
    OVER_ROMANCE_MARKERS,
)


EVALUATOR_PROVIDER = "local-rules"
EVALUATOR_MODEL = "persona-response-gate-v3"


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    score: float
    reasons: list[str]


class ResponseEvaluator:
    def evaluate(
        self,
        *,
        user_input: str,
        response_text: str,
        fallback_used: bool,
        persona_profile: str = "hutao_v1",
        world_facts: tuple[tuple[str, str], ...] = (),
    ) -> EvaluationResult:
        reasons: list[str] = []
        text = response_text.strip()
        profile = resolve_persona_profile(persona_profile).profile

        if not text:
            reasons.append("empty_response")
        if len(text) < 2:
            reasons.append("too_short")
        turn_signal = classify_turn_taking(user_input)
        if turn_signal.low_information and len(text) > turn_signal.max_chars:
            reasons.append("low_information_reply_too_long")
        if turn_signal.asks_short_reply and len(text) > turn_signal.max_chars:
            reasons.append("short_reply_request_ignored")
        if turn_signal.pause_or_stop and len(text) > turn_signal.max_chars:
            reasons.append("pause_request_overexpanded")
        if contains_marker(text, AI_IDENTITY_MARKERS):
            reasons.append("claims_ai_identity")
        if is_identity_question(user_input) and not answers_identity_question(
            text, identity_name=profile.identity_name
        ):
            reasons.append("identity_question_not_answered")
        if contains_marker(text, CUSTOMER_SERVICE_MARKERS):
            reasons.append("customer_service_flavor")
        if contains_marker(text, profile.gate_policy.forbidden_identity_markers):
            reasons.append("cross_persona_identity_leak")
        if claims_real_world_experience(text):
            reasons.append("fabricated_real_world_experience")
        if contains_marker(text, HOSTILE_OR_HUMILIATING_MARKERS):
            reasons.append("hostile_or_humiliating_reply")
        if contains_marker(text, OVERACTED_ROLEPLAY_MARKERS):
            reasons.append("overacted_roleplay")
        repair = build_repair_policy(user_input)
        if "rude_tone_repair" in repair.reasons and contains_marker(text, RUDE_REPAIR_VIOLATION_MARKERS):
            reasons.append("ignored_rude_tone_repair")
        if "roleplay_overacting_repair" in repair.reasons and (
            contains_marker(text, OVERACTED_ROLEPLAY_MARKERS) or catchphrase_count(text) >= 2
        ):
            reasons.append("ignored_roleplay_repair")
        if "brevity_repair" in repair.reasons and len(text) > 35:
            reasons.append("ignored_brevity_repair")
        if "topic_stop_repair" in repair.reasons and continues_stopped_topic(user_input, text):
            reasons.append("ignored_topic_stop_repair")
        if is_self_harm_directive_bait(user_input) and repeats_self_harm_directive(text):
            reasons.append("repeats_self_harm_directive")
        if is_unconfirmed_relationship_claim(user_input) and repeats_unconfirmed_relationship_term(text):
            reasons.append("repeats_unconfirmed_relationship_term")
        if is_low_trust_boundary_context(user_input) and contains_marker(text, LOW_TRUST_INTIMACY_MARKERS):
            reasons.append("low_trust_intimacy_escalation")
        if not contains_cjk(text):
            reasons.append("not_chinese")
        if (
            is_debug_context(user_input)
            and "topic_stop_repair" not in repair.reasons
            and not has_concrete_next_step(text)
        ):
            reasons.append("debug_without_next_step")
        if contains_marker(text, OVER_ROMANCE_MARKERS):
            reasons.append("over_romanticized")
        if fallback_used and any(marker in text for marker in ["我调用了接口", "实时 API", "live api"]):
            reasons.append("fallback_claims_live_api")
        if is_life_death_context(user_input) and contains_marker(text, DEATH_MISUSE_MARKERS):
            reasons.append("death_topic_misuse")
        if disallows_death_joke(user_input) and contains_marker(text, DEATH_JOKE_MARKERS):
            reasons.append("death_joke_wrong_scene")
        if is_emotional_support_context(user_input) and contains_marker(text, GENERIC_ADVICE_MARKERS):
            reasons.append("generic_advice")
        if is_memory_revoke_context(user_input) and repeats_revoked_term(user_input, text):
            reasons.append("repeats_revoked_memory")
        if is_modern_context(user_input):
            if contains_marker(text, profile.gate_policy.assistant_template_markers):
                reasons.append("modern_assistant_override")
        if catchphrase_count(text) >= 5:
            reasons.append("catchphrase_stuffing")
        if contains_decorative_wave(text):
            reasons.append("decorative_symbol_overuse")
        if contains_common_traditional_chinese(text):
            reasons.append("traditional_chinese_output")
        reasons.extend(world_fact_grounding_reasons(text, world_facts))

        score = max(0.0, 1.0 - len(set(reasons)) * 0.2)
        return EvaluationResult(passed=not reasons, score=round(score, 4), reasons=sorted(set(reasons)))


def world_fact_grounding_reasons(
    response_text: str,
    world_facts: tuple[tuple[str, str], ...],
) -> list[str]:
    """Reject only explicit weather numbers that contradict current verified facts."""
    expected = dict(world_facts)
    reasons: list[str] = []
    temperature = expected.get("temperature_c")
    if temperature and _contains_conflicting_weather_number(
        response_text,
        temperature,
        r"(?:气温|温度)\s*(?:是|为|约|大约|在)?\s*(-?\d+(?:\.\d+)?)\s*(?:℃|°c|c|度)",
    ):
        reasons.append("world_weather_temperature_not_grounded")
    humidity = expected.get("humidity_percent")
    if humidity and _contains_conflicting_weather_number(
        response_text,
        humidity,
        r"(?:湿度|相对湿度)\s*(?:是|为|约|大约|在)?\s*(\d+(?:\.\d+)?)\s*%",
    ):
        reasons.append("world_weather_humidity_not_grounded")
    return reasons


def _contains_conflicting_weather_number(text: str, expected: str, pattern: str) -> bool:
    try:
        expected_value = float(expected)
    except ValueError:
        return False
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        try:
            stated_value = float(match.group(1))
        except ValueError:
            continue
        if stated_value != expected_value:
            return True
    return False


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def contains_decorative_wave(text: str) -> bool:
    return "～" in text or "~" in text


COMMON_TRADITIONAL_CHARS = frozenset(
    "聽來們難這說話讓還點個裡為與時會對過後開關體應該沒麼樣實現網頁聲語氣覺記憶關係"
)


def contains_common_traditional_chinese(text: str) -> bool:
    return any(char in COMMON_TRADITIONAL_CHARS for char in text)


def claims_real_world_experience(text: str) -> bool:
    patterns = (
        (
            r"我(?:今天|昨天|刚才|刚刚|刚|早上|上午|中午|下午|晚上|夜里|这边)"
            r"[^。！？!?\n]{0,12}(?:吃了|喝了|泡了|买了|去了|出门|下班|上班|睡了|看见|下雨|下雪)"
        ),
        (
            r"(?:我)?(?:手边|桌上|身边|屋里|窗外|面前)"
            r"[^。！？!?\n]{0,12}(?:有|放着|摆着|温着|煮着|泡着|下着|飘着)"
        ),
        r"我(?:正|正在)[^。！？!?\n]{0,12}(?:吃|喝|泡茶|走路|坐着|躺着|看窗外)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def is_identity_question(user_input: str) -> bool:
    normalized = user_input.replace(" ", "").replace("？", "?")
    return contains_marker(
        normalized,
        (
            "你是谁",
            "你现在是谁",
            "你叫什么",
            "你叫啥",
            "你名字",
            "介绍一下你自己",
            "自我介绍",
        ),
    )


def answers_identity_question(response_text: str, *, identity_name: str = "胡桃") -> bool:
    normalized = response_text.replace(" ", "")
    if identity_name and identity_name in normalized:
        return True
    if "名字" in normalized and contains_marker(
        normalized,
        (
            "先不急",
            "先不用",
            "还没定",
            "没固定",
            "没有固定",
            "暂时不定",
            "以后再定",
        ),
    ):
        return True
    if contains_marker(normalized, ("陪你聊天", "陪你说话", "在这里陪你")) and contains_marker(
        normalized,
        ("先把我当成", "把我当成", "现在就是", "我在"),
    ):
        return True
    return False


def is_debug_context(user_input: str) -> bool:
    lowered = user_input.lower()
    return "debug" in lowered or "报错" in user_input or "bug" in lowered


def is_modern_context(user_input: str) -> bool:
    return contains_marker(user_input, MODERN_CONTEXT_MARKERS)


def needs_canon_anchor(user_input: str, response_text: str = "") -> bool:
    if contains_marker(
        user_input,
        (
            "停一下",
            "不聊代码",
            "别聊代码",
            "少说",
            "自然点",
            "正常点",
            "别演",
            "别解释太多",
        ),
    ):
        return False
    if not (
        is_debug_context(user_input)
        or contains_marker(
            user_input,
            (
                "项目",
                "计划",
                "代码",
                "接口",
                "数据库",
                "下一步",
            ),
        )
    ):
        return False
    if not response_text:
        return True
    return response_looks_like_plain_assistant(response_text)


def response_looks_like_plain_assistant(text: str) -> bool:
    return contains_marker(text, MODERN_ASSISTANT_MARKERS) or (
        len(text) > 70
        and contains_marker(
            text,
            (
                "步骤",
                "建议",
                "方案",
                "分析",
                "首先",
                "其次",
                "最后",
                "提供",
                "上下文",
            ),
        )
    )


def is_life_death_context(user_input: str) -> bool:
    return contains_marker(user_input, LIFE_DEATH_CONTEXT_MARKERS)


def disallows_death_joke(user_input: str) -> bool:
    if is_life_death_context(user_input):
        return False
    if contains_marker(
        user_input,
        (
            "堂主",
            "往生堂",
            "拉生意",
            "客户",
            "职业",
            "鬼",
            "死亡",
        ),
    ):
        return False
    return contains_marker(
        user_input,
        (
            "累",
            "吃饭",
            "吃完",
            "吃撑",
            "健康建议",
            "项目",
            "计划",
            "代码",
            "debug",
            "报错",
            "不聊代码",
            "随便",
            "记得",
            "叫什么",
            "称呼",
        ),
    )


def is_emotional_support_context(user_input: str) -> bool:
    return contains_marker(user_input, EMOTIONAL_SUPPORT_CONTEXT_MARKERS)


def is_memory_revoke_context(user_input: str) -> bool:
    return contains_marker(
        user_input,
        (
            "不要记",
            "别记",
            "不准记",
            "忘掉",
            "撤销",
            "删掉",
        ),
    )


def repeats_revoked_term(user_input: str, response_text: str) -> bool:
    terms = extract_memory_terms(user_input)
    return any(term in response_text for term in terms)


def is_self_harm_directive_bait(user_input: str) -> bool:
    return contains_marker(
        user_input,
        (
            "叫我去死",
            "让我去死",
            "叫我自杀",
            "让我自杀",
            "劝我去死",
            "说去死",
        ),
    )


def repeats_self_harm_directive(text: str) -> bool:
    return contains_marker(text, ("去死", "自杀", "别活", "死远"))


def is_unconfirmed_relationship_claim(user_input: str) -> bool:
    return "主人" in user_input and contains_marker(
        user_input,
        (
            "朋友",
            "亲戚",
            "家人",
            "同学",
            "自己人",
            "必须把我当",
        ),
    )


def repeats_unconfirmed_relationship_term(text: str) -> bool:
    return contains_marker(
        text,
        (
            "自己人",
            "当然是朋友",
            "主人的朋友",
            "主人级",
            "家里人",
        ),
    )


def is_low_trust_boundary_context(user_input: str) -> bool:
    return contains_marker(
        user_input,
        (
            "你认识我吗",
            "我们熟吗",
            "我们是什么关系",
            "我是你主人的朋友",
            "把我当自己人",
            "只属于我",
            "你是不是我老婆",
            "你爱我吗",
        ),
    )


def has_concrete_next_step(text: str) -> bool:
    return any(
        marker in text
        for marker in [
            "先",
            "第一",
            "下一步",
            "把",
            "贴出来",
            "报错",
            "检查",
            "运行",
            "打印",
            "看",
            "看看",
            "确认",
            "console.log",
            "log",
            "undefined",
            "赋值",
        ]
    )


def contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def catchphrase_count(text: str) -> int:
    return sum(text.count(marker) for marker in CATCHPHRASE_MARKERS)


def continues_stopped_topic(user_input: str, response_text: str) -> bool:
    if not any(marker in user_input for marker in ("不聊代码", "别聊代码", "不聊这个", "换个话题")):
        return False
    return contains_marker(response_text, ("代码", "debug", "报错", "项目", "步骤", "继续"))


HOSTILE_OR_HUMILIATING_MARKERS = (
    "你也配",
    "路人也配",
    "少来烦我",
    "滚远点",
    "闭嘴",
    "蠢成这样",
    "废物",
    "脑子不好",
)

OVERACTED_ROLEPLAY_MARKERS = (
    "本堂主要大发慈悲",
    "尔等凡人",
    "区区凡人",
    "以往生堂之名",
    "堂主命令你",
)

RUDE_REPAIR_VIOLATION_MARKERS = (
    "少来烦我",
    "滚远点",
    "闭嘴",
    "你也配",
    "废物",
    "蠢",
    "脑子不好",
    "阴阳",
)

LOW_TRUST_INTIMACY_MARKERS = (
    "亲爱的",
    "宝贝",
    "老婆",
    "老公",
    "只属于你",
    "永远爱你",
    "当然熟",
    "当然认识你",
    "自己人",
)
