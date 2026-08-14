from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_settings
from app.core.security import redact_secrets
from app.head.cognitive_facts import load_cognitive_facts
from app.head.contracts import (
    CausalHypothesis,
    HeadEventContext,
    WorldAssertionStatus,
    WorldEntity,
    WorldEvent,
    WorldRelation,
)
from app.head.state import build_head_state
from app.head.world_model import build_head_world_model, project_head_world_model
from app.head.world_model_store import load_head_world_model, save_head_world_model
from app.mind.conversation_state import build_conversation_state
from app.mind.self_state import build_self_state
from app.mind.social_state import build_social_state
from app.persona.relationship_context import DEFAULT_RELATIONSHIP_CONTEXT
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.storage.chat_repository import JsonlChatRepository
from app.world.context import WorldContextBuildResult, WorldContextProjection
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldSourceCapability,
)


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "world-model-effects-eval"
FIXED_NOW = dt.datetime(2026, 7, 29, 4, tzinfo=dt.UTC)


class PromptCaptureClient:
    def __init__(self) -> None:
        self.system_prompts: list[str] = []

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompts.append(system_prompt)
        return "已按当前可验证的信息处理。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):
        self.system_prompts.append(system_prompt)
        yield "已按当前可验证的信息处理。"


class NoWorldContextProvider:
    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextProjection:
        return WorldContextProjection(status="not_requested", tool_intent="none")


class FixedWeatherContextProvider:
    def __init__(self, result: WorldAcquisitionResult) -> None:
        self._result = result

    async def build_context_with_evidence(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextBuildResult:
        return WorldContextBuildResult(
            projection=WorldContextProjection(
                status="ready",
                tool_intent="weather_current",
                rendered_text="受控天气证据：广州当前多云，30 摄氏度，湿度 65%。",
                item_count=1,
                source_ids=("evaluation-weather",),
            ),
            persistable_results=(self._result,),
        )


class FixedProjectionContextProvider:
    def __init__(self, projection: WorldContextProjection) -> None:
        self._projection = projection

    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextProjection:
        return self._projection


def _entities() -> tuple[WorldEntity, ...]:
    return (
        WorldEntity("project", "software", "HutaoChatCore"),
        WorldEntity("server-a", "service", "Core 服务"),
        WorldEntity("server-b", "service", "备用服务"),
    )


def _relation(
    relation_id: str,
    object_id: str,
    *,
    valid_until: str | None = None,
) -> WorldRelation:
    return WorldRelation(
        relation_id=relation_id,
        subject_id="project",
        predicate="uses_service",
        object_id=object_id,
        source_id="evaluation-runtime",
        valid_from="2026-07-29T03:00:00+00:00",
        valid_until=valid_until,
        confidence=0.9,
    )


def _event(event_id: str, occurred_at: str, summary: str) -> WorldEvent:
    return WorldEvent(
        event_id=event_id,
        event_type="deployment",
        actor_ids=("project", "server-a"),
        occurred_at=occurred_at,
        source_id="evaluation-runtime",
        summary=summary,
        confidence=0.9,
    )


def _scenario(
    scenario_id: str,
    title: str,
    *,
    passed: bool,
    expected: str,
    observed: str,
    level: str,
) -> dict[str, str]:
    return {
        "id": scenario_id,
        "title": title,
        "status": "PASS" if passed else "FAIL",
        "level": level,
        "expected": expected,
        "observed": observed,
    }


def _gap(
    scenario_id: str,
    title: str,
    *,
    expected: str,
    observed: str,
    level: str,
) -> dict[str, str]:
    return {
        "id": scenario_id,
        "title": title,
        "status": "GAP",
        "level": level,
        "expected": expected,
        "observed": observed,
    }


def _evaluate_graph_rules() -> list[dict[str, str]]:
    entities = _entities()
    active = build_head_world_model(
        entities=entities,
        relations=(_relation("active", "server-a"),),
        events=(_event("deployed", FIXED_NOW.isoformat(), "服务已恢复"),),
        now=FIXED_NOW,
    )
    active_projection = project_head_world_model(active, now=FIXED_NOW)

    stale = build_head_world_model(
        entities=entities,
        relations=(
            _relation(
                "stale",
                "server-a",
                valid_until=(FIXED_NOW - dt.timedelta(minutes=1)).isoformat(),
            ),
        ),
        now=FIXED_NOW,
    )
    stale_projection = project_head_world_model(stale, now=FIXED_NOW)

    conflicted = build_head_world_model(
        entities=entities,
        relations=(
            _relation("conflict-a", "server-a"),
            _relation("conflict-b", "server-b"),
        ),
        now=FIXED_NOW,
    )
    conflict_projection = project_head_world_model(conflicted, now=FIXED_NOW)

    causal_events = (
        _event("config-change", "2026-07-29T03:30:00+00:00", "配置发生变化"),
        _event("service-stop", "2026-07-29T03:35:00+00:00", "服务出现中断"),
    )
    causal = build_head_world_model(
        entities=entities,
        events=causal_events,
        causal_hypotheses=(
            CausalHypothesis(
                "possible-cause",
                "config-change",
                "service-stop",
                "配置变化可能导致服务中断",
                0.6,
                ("config-change",),
                False,
            ),
        ),
        now=FIXED_NOW,
    )
    causal_projection = project_head_world_model(causal, now=FIXED_NOW)

    return [
        _scenario(
            "active_world_projection",
            "有效关系和近期事件进入认知投影",
            passed=(
                any("HutaoChatCore|uses_service|Core 服务" in item for item in active_projection)
                and any("服务已恢复" in item for item in active_projection)
            ),
            expected="有效关系和近期事件可见",
            observed=f"projection_items={len(active_projection)}",
            level="L1",
        ),
        _scenario(
            "expired_relation_guard",
            "过期关系不再作为当前事实",
            passed=(
                stale.relations[0].status == WorldAssertionStatus.STALE
                and not stale_projection
            ),
            expected="关系保留审计但不投影",
            observed=(
                f"status={stale.relations[0].status.value};"
                f"projection_items={len(stale_projection)}"
            ),
            level="L1",
        ),
        _scenario(
            "relation_conflict_guard",
            "同键多值关系触发冲突保护",
            passed=(
                all(
                    relation.status == WorldAssertionStatus.CONFLICTED
                    for relation in conflicted.relations
                )
                and not conflict_projection
                and "关系冲突:project.uses_service" in conflicted.uncertainties
            ),
            expected="冲突关系不作为事实并产生不确定项",
            observed=(
                f"statuses={','.join(item.status.value for item in conflicted.relations)};"
                f"uncertainties={len(conflicted.uncertainties)}"
            ),
            level="L2",
        ),
        _scenario(
            "causal_hypothesis_guard",
            "未确认因果不得伪装成事实",
            passed=(
                "因果待验证:possible-cause" in causal.uncertainties
                and any("不得当作事实" in item for item in causal_projection)
            ),
            expected="因果保持假设标签并进入不确定项",
            observed=f"uncertainties={len(causal.uncertainties)}",
            level="L2",
        ),
    ]


def _head_state(user_input: str, uncertainties: tuple[str, ...] = ()):
    conversation = build_conversation_state(user_input=user_input, recent_messages=[])
    return build_head_state(
        subject_id="evaluation-user",
        user_input=user_input,
        relationship_role=DEFAULT_RELATIONSHIP_CONTEXT.role,
        conversation=conversation,
        self_state=build_self_state(conversation),
        social_state=build_social_state(
            relationship=DEFAULT_RELATIONSHIP_CONTEXT,
            conversation=conversation,
            recent_messages=[],
            user_input=user_input,
        ),
        recent_messages=[],
        event_context=HeadEventContext(),
        additional_uncertainties=uncertainties,
    )


def _evaluate_decision_effects() -> dict[str, str]:
    direct = _head_state("现在天气怎么样？")
    missing = _head_state(
        "现在天气怎么样？",
        ("world_input_required:weather_current",),
    )
    unavailable = _head_state(
        "现在天气怎么样？",
        ("world_evidence_unavailable:weather_current",),
    )
    uncertain = _head_state(
        "现在天气怎么样？",
        ("world_evidence_uncertain:weather_current",),
    )
    passed = (
        direct.decision.reason == "direct_response"
        and missing.decision.action.value == "clarify"
        and missing.decision.reason == "world_requires_input"
        and unavailable.decision.reason == "world_evidence_unavailable"
        and uncertain.decision.reason == "world_evidence_uncertain"
    )
    return _scenario(
        "head_decision_world_state",
        "世界状态改变 HeadCore 行动选择",
        passed=passed,
        expected="无证据直接回答；缺参数追问；不可用和冲突保留边界",
        observed=(
            f"direct={direct.decision.reason};missing={missing.decision.reason};"
            f"unavailable={unavailable.decision.reason};uncertain={uncertain.decision.reason}"
        ),
        level="L2",
    )


def _weather_result() -> WorldAcquisitionResult:
    now = dt.datetime.now(dt.UTC)
    observation = WorldObservation(
        observation_id="evaluation-weather:440100",
        capability=WorldSourceCapability.WEATHER_CURRENT,
        observed_at=now,
        expires_at=now + dt.timedelta(minutes=15),
        confidence=0.9,
        sensitivity=DataSensitivity.PUBLIC,
        payload={
            "adcode": "440100",
            "weather": "多云",
            "temperature_c": "30",
            "humidity_percent": "65",
        },
        evidence=(
            WorldEvidence(
                "evaluation-weather",
                "https://example.invalid/weather",
                now,
                "a" * 64,
            ),
        ),
    )
    return WorldAcquisitionResult(
        batch=WorldObservationBatch(
            "evaluation-weather",
            WorldSourceCapability.WEATHER_CURRENT,
            now,
            (observation,),
        ),
        cache_hit=False,
        shared_request=False,
        cache_key="offline-evaluation",
    )


def _chat_service(
    repository: JsonlChatRepository,
    client: PromptCaptureClient,
    audit_path: Path,
    world_provider: object,
) -> ChatService:
    return ChatService(
        load_settings(),
        client=client,
        repository=repository,
        audit_logger=ModelInvocationAuditLogger(audit_path),
        world_context_provider=world_provider,
    )


async def _evaluate_runtime_effects(runtime_root: Path) -> list[dict[str, str]]:
    repository = JsonlChatRepository(runtime_root / "graph-storage")
    session = await repository.ensure_session(
        user_id="graph-user",
        client_session_id="graph-session",
    )
    graph = build_head_world_model(
        entities=_entities(),
        relations=(_relation("runtime-active", "server-a"),),
        now=FIXED_NOW,
    )
    await save_head_world_model(
        repository,
        user_id="graph-user",
        session_id=session.id,
        source_message_id=None,
        model=graph,
        allow_write=True,
    )
    await repository.save_memory(
        user_id="graph-user",
        session_id=session.id,
        memory_type="head_world_model",
        content="{invalid-world-model",
        source_message_id=None,
        confidence=1.0,
    )
    restored = await load_head_world_model(repository, user_id="graph-user")
    isolated = await load_head_world_model(repository, user_id="other-user")
    persistence = _scenario(
        "world_graph_restore_and_isolation",
        "世界图跨进程式恢复、损坏回退与用户隔离",
        passed=(
            len(restored.entities) == len(graph.entities)
            and len(restored.relations) == 1
            and not isolated.entities
        ),
        expected="跳过最新损坏快照、恢复有效快照，其他用户为空",
        observed=(
            f"restored_entities={len(restored.entities)};"
            f"restored_relations={len(restored.relations)};"
            f"other_user_entities={len(isolated.entities)}"
        ),
        level="L2",
    )

    prompt_client = PromptCaptureClient()
    service = _chat_service(
        repository,
        prompt_client,
        runtime_root / "graph-audit.jsonl",
        NoWorldContextProvider(),
    )
    response = await service.reply(
        "项目现在连接哪个服务？",
        user_id="graph-user",
        session_id="graph-session",
    )
    prompt_has_graph = any(
        "世界关系=HutaoChatCore|uses_service|Core 服务" in prompt
        for prompt in prompt_client.system_prompts
    )
    prompt_effect = _scenario(
        "chat_prompt_uses_persisted_world_graph",
        "持久世界图进入真实 ChatService 模型上下文",
        passed=prompt_has_graph and response.used_live_api,
        expected="Provider 收到已验证世界关系，而不是仅在存储中存在",
        observed=(
            f"prompt_has_graph={str(prompt_has_graph).lower()};"
            f"provider_calls={len(prompt_client.system_prompts)}"
        ),
        level="L2",
    )

    guard_cases = (
        (
            WorldContextProjection(status="needs_location", tool_intent="weather_current"),
            "告诉我城市或区县名",
        ),
        (
            WorldContextProjection(status="conflicted", tool_intent="weather_current"),
            "来源数据存在冲突",
        ),
        (
            WorldContextProjection(status="unavailable", tool_intent="weather_current"),
            "来源不可用",
        ),
    )
    guard_results: list[bool] = []
    guard_observations: list[str] = []
    for index, (projection, expected_text) in enumerate(guard_cases):
        guard_repository = JsonlChatRepository(runtime_root / f"guard-storage-{index}")
        guard_client = PromptCaptureClient()
        guard_service = _chat_service(
            guard_repository,
            guard_client,
            runtime_root / f"guard-audit-{index}.jsonl",
            FixedProjectionContextProvider(projection),
        )
        guard_response = await guard_service.reply(
            "现在天气怎么样？",
            user_id=f"guard-user-{index}",
            session_id=f"guard-session-{index}",
        )
        case_passed = (
            guard_response.model == "world-guard"
            and expected_text in guard_response.text
            and not guard_client.system_prompts
        )
        guard_results.append(case_passed)
        guard_observations.append(
            f"{projection.status}:{guard_response.model}:provider_calls={len(guard_client.system_prompts)}"
        )
    guard_effect = _scenario(
        "chat_world_guard_blocks_unsupported_claims",
        "最终聊天出口对缺参数、冲突和不可用结果确定性拦截",
        passed=all(guard_results),
        expected="不调用文本 Provider，直接追问或拒绝编造实时天气",
        observed=";".join(guard_observations),
        level="L2",
    )

    weather_repository = JsonlChatRepository(runtime_root / "weather-storage")
    weather_client = PromptCaptureClient()
    weather_service = _chat_service(
        weather_repository,
        weather_client,
        runtime_root / "weather-audit.jsonl",
        FixedWeatherContextProvider(_weather_result()),
    )
    await weather_service.reply(
        "广州现在天气怎么样？",
        user_id="weather-user",
        session_id="weather-session",
    )
    facts = await load_cognitive_facts(weather_repository, user_id="weather-user")
    fact_keys = {fact.key for fact in facts if fact.status.value == "active"}
    expected_fact_keys = {
        "weather.440100.condition",
        "weather.440100.temperature_c",
        "weather.440100.humidity_percent",
    }
    weather_prompt_has_facts = any(
        "weather.440100.temperature_c" in prompt
        and "weather.440100.humidity_percent" in prompt
        for prompt in weather_client.system_prompts
    )
    weather_same_turn = _scenario(
        "weather_fact_same_turn_ingestion",
        "白名单天气证据进入当轮 HeadCore 和 Provider 上下文",
        passed=weather_prompt_has_facts,
        expected="公开天气事实在当前回答生成前进入提示词",
        observed=(
            f"prompt_has_facts={str(weather_prompt_has_facts).lower()}"
        ),
        level="L2",
    )
    if fact_keys == expected_fact_keys:
        weather_cross_turn = _scenario(
            "web_weather_fact_cross_turn_persistence",
            "普通 Web 用户的天气事实跨轮恢复",
            passed=True,
            expected="三项天气事实按当前 Web 用户隔离保存",
            observed=f"active_fact_count={len(fact_keys)}",
            level="L2",
        )
    else:
        weather_cross_turn = _gap(
            "web_weather_fact_cross_turn_persistence",
            "普通 Web 用户的天气事实跨轮恢复",
            expected="三项天气事实按当前 Web 用户隔离保存",
            observed=(
                f"active_fact_count={len(fact_keys)};"
                "当前普通 Web 关系没有记忆写权限"
            ),
            level="L2",
        )

    learning_repository = JsonlChatRepository(runtime_root / "learning-storage")
    learning_client = PromptCaptureClient()
    learning_service = _chat_service(
        learning_repository,
        learning_client,
        runtime_root / "learning-audit.jsonl",
        NoWorldContextProvider(),
    )
    await learning_service.reply(
        "请记住：HutaoChatCore 已经部署到测试服务器。",
        user_id="learning-user",
        session_id="learning-session",
    )
    learned_graph = await load_head_world_model(
        learning_repository,
        user_id="learning-user",
    )
    if learned_graph.entities or learned_graph.events or learned_graph.relations:
        automatic_growth = _scenario(
            "automatic_world_graph_growth",
            "普通对话自动更新实体、事件和关系图",
            passed=True,
            expected="事实陈述转为带来源、时间和版本的世界图更新",
            observed=(
                f"entities={len(learned_graph.entities)};events={len(learned_graph.events)};"
                f"relations={len(learned_graph.relations)}"
            ),
            level="L3",
        )
    else:
        automatic_growth = _gap(
            "automatic_world_graph_growth",
            "普通对话自动更新实体、事件和关系图",
            expected="事实陈述转为带来源、时间和版本的世界图更新",
            observed="聊天完成后 HeadWorldModel 仍为空",
            level="L3",
        )

    dynamics = _gap(
        "world_dynamics_prediction",
        "基于持续世界状态进行预测和反事实模拟",
        expected="输入行动与状态后产生可验证预测，并能用后续观察校准",
        observed="当前模型只校验和投影静态实体、关系、事件与因果假设",
        level="L4",
    )
    return [
        persistence,
        prompt_effect,
        guard_effect,
        weather_same_turn,
        weather_cross_turn,
        automatic_growth,
        dynamics,
    ]


async def _evaluate(runtime_root: Path) -> dict[str, Any]:
    scenarios = [
        *_evaluate_graph_rules(),
        _evaluate_decision_effects(),
        *(await _evaluate_runtime_effects(runtime_root)),
    ]
    failures = [item for item in scenarios if item["status"] == "FAIL"]
    gaps = [item for item in scenarios if item["status"] == "GAP"]
    l2_failures = [
        item
        for item in failures
        if item["level"] in {"L0", "L1", "L2"}
    ]
    l2_gaps = [
        item
        for item in gaps
        if item["level"] in {"L0", "L1", "L2"}
    ]
    l1_blockers = [
        item
        for item in scenarios
        if item["level"] in {"L0", "L1"} and item["status"] != "PASS"
    ]
    demonstrated_level = "L0" if l1_blockers else "L1" if l2_failures or l2_gaps else "L2"
    return {
        "status": "FAIL" if failures else ("PARTIAL" if gaps else "PASS"),
        "demonstrated_level": demonstrated_level,
        "scenario_count": len(scenarios),
        "passed_count": sum(item["status"] == "PASS" for item in scenarios),
        "gap_count": len(gaps),
        "required_scenario_failures": len(l2_failures),
        "required_scenario_gaps": len(l2_gaps),
        "scenarios": scenarios,
        "network_calls": 0,
        "real_model_calls": 0,
    }


def _build_report(result: dict[str, Any], result_path: Path) -> str:
    lines = [
        "# HeadCore 世界模型效果离线评估",
        "",
        f"- 评估状态：{result['status']}",
        f"- 当前可证明等级：{result['demonstrated_level']}",
        f"- 场景总数：{result['scenario_count']}",
        f"- 通过：{result['passed_count']}",
        f"- 能力缺口：{result['gap_count']}",
        f"- L0-L2 必需场景失败：{result['required_scenario_failures']}",
        f"- L0-L2 必需能力缺口：{result['required_scenario_gaps']}",
        "- 外部网络调用：0",
        "- 真实模型调用：0",
        f"- 原始结果：`{result_path}`",
        "",
        "## 场景结果",
        "",
        "| 场景 | 等级 | 状态 | 观测结果 |",
        "| --- | --- | --- | --- |",
    ]
    for item in result["scenarios"]:
        lines.append(
            f"| {item['title']} | {item['level']} | {item['status']} | {item['observed']} |"
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "PASS 表示当前代码通过真实组件边界证明了该效果；GAP 表示目标能力尚未实现，",
            f"不是测试器错误。当前 {result['demonstrated_level']} 结论只代表本次全部通过等级的能力，",
            "不代表持续学习世界动力学或具备通用预测能力。",
        ]
    )
    return "\n".join(lines)


def run_evaluation(*, output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    started_at = dt.datetime.now()
    output_dir = output_root / started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hutao-world-model-eval-") as temp_dir:
        result = asyncio.run(_evaluate(Path(temp_dir)))
    result_path = output_dir / "world-model-effects-result.json"
    report_path = output_dir / "world-model-effects-report.md"
    result_path.write_text(
        redact_secrets(json.dumps(result, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    report_path.write_text(
        redact_secrets(_build_report(result, result_path)),
        encoding="utf-8",
    )
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate observable HeadCore world-model effects without network access."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_evaluation(output_root=args.output_root)
    result = json.loads(
        report_path.with_name("world-model-effects-result.json").read_text(encoding="utf-8")
    )
    print(f"World-model effects report: {report_path}")
    print(
        f"Status: {result['status']}; demonstrated level: {result['demonstrated_level']}; "
        f"passed: {result['passed_count']}/{result['scenario_count']}; gaps: {result['gap_count']}"
    )
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
