from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.head.contracts import HeadState
from app.mind.self_state import SelfState
from app.mind.social_state import SocialState


def render_head_projection(state: HeadState) -> str:
    known = "；".join(state.known_context) or "无"
    unknown = "；".join(state.uncertainties) or "无"
    communication = state.communication
    acts = "、".join(
        act.value for act in (communication.primary_act, *communication.secondary_acts)
    )
    hypotheses = "；".join(
        f"{item.kind}(置信度={item.confidence:.2f}，待确认={item.needs_confirmation})"
        for item in communication.hypotheses
    ) or "无"
    policy = communication.turn_policy
    feedback = state.feedback
    reflection = feedback.reflection
    adaptive = state.adaptive_policy
    plan = state.plan
    candidate_summary = "；".join(
        f"{index}:{candidate.action.value}/score={candidate.score.total:.4f}/"
        f"boundary={candidate.score.boundary_risk:.2f}/moralizing={candidate.score.moralizing_risk:.2f}/"
        f"fabrication={candidate.score.fabrication_risk:.2f}"
        for index, candidate in enumerate(plan.candidates)
    )
    return "\n".join(
        [
            "HeadCore 本轮认知快照（内部控制信息，不向用户复述）：",
            f"对象={state.subject_id}；关系={state.relationship_role}；社交边界={state.social_boundary}。",
            f"已知={known}。",
            f"不确定={unknown}。",
            f"沟通行为={acts}；用户心理假设={hypotheses}。假设不是事实，不得写入确定记忆或直接断言。",
            f"话轮策略=长度:{policy.response_length}，主动性:{policy.initiative}，最多追问:{policy.question_budget}，建议预算:{policy.advice_budget}，人格强度:{policy.persona_intensity:.2f}。",
            f"表达约束={'、'.join(policy.constraints) or '无'}。",
            f"上一行动反馈={feedback.outcome.value}；上一行动={feedback.previous_action}；反馈信号={'、'.join(feedback.signals) or '无'}。",
            (
                "结构化反思="
                f"错误:{reflection.mistake_type}；原因:{reflection.cause}；"
                f"更好行动:{reflection.better_action}；候选策略:{reflection.policy_candidate}。"
                "只修正本轮策略，不因单次反馈写成永久用户偏好。"
                if reflection is not None
                else "结构化反思=无。"
            ),
            (
                "短期自适应策略="
                f"active={adaptive.active}；version={adaptive.version}；证据数={adaptive.evidence_count}；"
                f"建议预算上限={adaptive.advice_budget_cap}；歧义澄清偏置={adaptive.clarification_bias}；"
                f"人格强度上限={adaptive.persona_intensity_cap}；原因={'、'.join(adaptive.reasons) or '无'}；"
                f"过期={adaptive.expires_at or '无'}。"
                "这是可过期、可重置的短期策略，不改变身份、权限或长期人格。"
            ),
            f"行动规划=复杂场景:{plan.complex_scene}；候选数:{len(plan.candidates)}；候选:{candidate_summary}；选择:{plan.selected_index}；依据:{plan.rationale}。",
            f"本轮行动={state.decision.action.value}；目标={state.decision.objective}；依据={state.decision.reason}。",
            "只使用已确认信息；不确定信息需要追问或调用已有工具，不要自行补全。",
        ]
    )


def render_continuity_timeline(
    state: HeadState,
    *,
    self_state: SelfState,
    social_state: SocialState,
    now: dt.datetime | None = None,
) -> str:
    current_time = now or dt.datetime.now(dt.UTC)
    if current_time.tzinfo is None:
        raise ValueError("continuity timeline time must include a timezone")
    local_time = current_time.astimezone(ZoneInfo("Asia/Shanghai"))
    recent_events = tuple(
        value for value in state.known_context if value.startswith("近期经历[")
    )[-4:]
    return "\n".join(
        [
            "连续性时间线（内部控制信息）：",
            f"当前时刻={local_time.strftime('%Y-%m-%d %H:%M %Z')}；当前话题={state.current_topic}。",
            (
                "当前自身状态="
                f"情绪:{self_state.mood}，能量:{self_state.energy}，"
                f"注意力:{self_state.focus}，张力:{self_state.tension}。"
            ),
            (
                "当前社交状态="
                f"熟悉度:{social_state.familiarity}，信任:{social_state.trust_band}，"
                f"边界:{social_state.boundary_mode}。"
            ),
            f"当前任务={state.active_task}；本轮目标={state.decision.objective}。",
            f"近期真实经历={'；'.join(recent_events) or '无已记录事件'}。",
            "这是后端状态投影，只用于维持跨轮一致性；不得编造现实经历或把内部状态说成自我意识。",
            "只输出给用户可见的回复，不要输出 <internal_thought>、分析过程或任何内部标签。",
        ]
    )
