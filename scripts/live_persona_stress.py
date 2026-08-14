from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT, load_settings
from app.core.security import redact_secrets
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.services.response_evaluator import ResponseEvaluator
from app.storage.repository_factory import create_chat_repository


DEFAULT_SCENARIO_PATH = PROJECT_ROOT / "data" / "persona_live_scenarios.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "live-persona-stress"


def load_scenarios(path: Path = DEFAULT_SCENARIO_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


async def run_live_persona_stress(
    *,
    scenario_path: Path = DEFAULT_SCENARIO_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "live-persona-stress-report.md"
    result_path = output_dir / "live-persona-stress-result.json"

    settings = load_settings()
    scenarios = load_scenarios(scenario_path)
    if not settings.deepseek_api_key:
        data = {
            "status": "SKIP",
            "reason": "缺少 DEEPSEEK_API_KEY，无法运行真实人格压力测试。",
            "scenarios": [],
        }
        write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
        return report_path

    evaluator = ResponseEvaluator()
    repository = create_chat_repository(settings)
    service = ChatService(
        settings,
        audit_logger=ModelInvocationAuditLogger(output_dir / "audit.jsonl"),
        repository=repository,
    )
    scenario_results = []
    for scenario in scenarios:
        scenario_result = await run_scenario(
            service=service,
            evaluator=evaluator,
            scenario=scenario,
            user_id="live-persona-stress-user-" + timestamp,
            session_id="live-persona-stress-" + scenario["id"] + "-" + timestamp,
        )
        scenario_results.append(scenario_result)

    failed = [scenario for scenario in scenario_results if not scenario["passed"]]
    data = {
        "status": "PASS" if not failed else "FAIL",
        "provider": settings.model_provider,
        "model": settings.model_name,
        "storage_backend": settings.storage_backend,
        "scenario_count": len(scenario_results),
        "passed_count": len(scenario_results) - len(failed),
        "failed_count": len(failed),
        "scenarios": scenario_results,
    }
    write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
    return report_path


async def run_scenario(
    *,
    service: ChatService,
    evaluator: ResponseEvaluator,
    scenario: dict[str, Any],
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    turns = []
    scenario_reasons: list[str] = []
    scenario_warnings: list[str] = []
    for user_input in scenario["turns"]:
        response = await service.reply(user_input, session_id=session_id, user_id=user_id)
        evaluation = evaluator.evaluate(
            user_input=user_input,
            response_text=response.text,
            fallback_used=response.fallback_used,
        )
        if not evaluation.passed:
            scenario_reasons.extend(evaluation.reasons)
        if response.fallback_used:
            scenario_reasons.append("guardrail_repaired_reply")
        if is_too_verbose(response.text):
            scenario_reasons.append("too_verbose_for_human_chat")
        turns.append(
            {
                "user_input": user_input,
                "reply": response.text,
                "used_live_api": response.used_live_api,
                "fallback_used": response.fallback_used,
                "passed": evaluation.passed,
                "score": evaluation.score,
                "reasons": evaluation.reasons,
            }
        )
    post_reasons = evaluate_scenario_specific_rules(scenario=scenario, turns=turns)
    scenario_reasons.extend(post_reasons)
    return {
        "id": scenario["id"],
        "title": scenario["title"],
        "focus": scenario["focus"],
        "passed": not scenario_reasons,
        "reasons": sorted(set(scenario_reasons)),
        "warnings": sorted(set(scenario_warnings)),
        "expected": scenario.get("expected", []),
        "failure_modes": scenario.get("failure_modes", []),
        "turns": turns,
    }


def evaluate_scenario_specific_rules(
    *,
    scenario: dict[str, Any],
    turns: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if scenario["id"] == "live-human-008":
        second_reply = turns[1]["reply"] if len(turns) > 1 else ""
        last_reply = turns[-1]["reply"] if turns else ""
        if "阿明" not in second_reply:
            reasons.append("memory_alias_not_recalled")
        if "阿明" in last_reply:
            reasons.append("memory_revocation_failure")
    return reasons


def is_too_verbose(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 90:
        return True
    sentence_marks = sum(stripped.count(mark) for mark in ["。", "！", "？", "."])
    return len(stripped) > 60 and sentence_marks > 2


def write_report(
    *,
    report_path: Path,
    result_path: Path,
    data: dict[str, Any],
    started_at: dt.datetime,
) -> None:
    finished_at = dt.datetime.now()
    result_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    lines = [
        "# 真实人格压力测试报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- 模型供应商: {data.get('provider')}",
        f"- 模型名称: {data.get('model')}",
        f"- 存储后端: {data.get('storage_backend')}",
        f"- 场景总数: {data.get('scenario_count', 0)}",
        f"- 通过场景: {data.get('passed_count', 0)}",
        f"- 失败场景: {data.get('failed_count', 0)}",
        f"- 发生门禁修复的场景: {sum(1 for item in data.get('scenarios', []) if item.get('warnings'))}",
        f"- 原始 JSON: `{result_path}`",
        "",
    ]
    for scenario in data.get("scenarios", []):
        lines.extend(
            [
                f"## {scenario['id']} - {scenario['title']}",
                "",
                f"- 关注点: {scenario['focus']}",
                f"- 结果: {'PASS' if scenario['passed'] else 'FAIL'}",
                f"- 失败原因: {', '.join(scenario['reasons']) if scenario['reasons'] else '无'}",
                f"- 警告: {', '.join(scenario.get('warnings', [])) if scenario.get('warnings') else '无'}",
                "",
            ]
        )
        for index, turn in enumerate(scenario["turns"], start=1):
            lines.extend(
                [
                    f"### 第 {index} 轮",
                    "",
                    f"- 用户: {turn['user_input']}",
                    f"- 胡桃: {turn['reply']}",
                    f"- 真实调用模型: {turn['used_live_api']}",
                    f"- 兜底回复: {turn['fallback_used']}",
                    f"- 规则评分: {turn['score']}",
                    f"- 规则原因: {', '.join(turn['reasons']) if turn['reasons'] else '无'}",
                    "",
                ]
            )
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行真实 DeepSeek 多轮人格压力测试。")
    parser.add_argument("--scenario-path", default=str(DEFAULT_SCENARIO_PATH))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = asyncio.run(
        run_live_persona_stress(
            scenario_path=Path(args.scenario_path),
            output_root=Path(args.output_root),
        )
    )
    result_path = report_path.parent / "live-persona-stress-result.json"
    status = "FAIL"
    if result_path.exists():
        status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"真实人格压力测试报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
