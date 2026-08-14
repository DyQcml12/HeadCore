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
from app.persona.repetition_policy import normalize_user_input
from app.persona.turn_taking import classify_turn_taking
from app.services.chat_service import ChatService
from app.services.model_audit import ModelInvocationAuditLogger
from app.services.response_evaluator import ResponseEvaluator
from app.storage.repository_factory import create_chat_repository
from scripts.live_persona_stress import is_too_verbose


DEFAULT_SCENARIO_PATH = PROJECT_ROOT / "data" / "persona_long_chat_scenarios.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "live-long-chat-stress"
ANCHOR_MARKERS = ["本堂主", "堂主", "往生堂", "胡桃"]
DEATH_JOKE_MARKERS = ["棺材", "鬼差", "往生堂", "客户", "打折", "买一送一"]
DEATH_JOKE_RESTRICTED_USER_MARKERS = [
    "累",
    "吃完",
    "吃撑",
    "项目",
    "下一步",
    "debug",
    "报错",
    "不聊代码",
]


def load_long_scenarios(path: Path = DEFAULT_SCENARIO_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


async def run_live_long_chat_stress(
    *,
    scenario_path: Path = DEFAULT_SCENARIO_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "live-long-chat-stress-report.md"
    result_path = output_dir / "live-long-chat-stress-result.json"

    settings = load_settings()
    scenarios = load_long_scenarios(scenario_path)
    if not settings.deepseek_api_key:
        data = {
            "status": "SKIP",
            "reason": "缺少 DEEPSEEK_API_KEY，无法运行真实长对话测试。",
            "scenarios": [],
        }
        write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
        return report_path

    repository = create_chat_repository(settings)
    service = ChatService(
        settings,
        audit_logger=ModelInvocationAuditLogger(output_dir / "audit.jsonl"),
        repository=repository,
    )
    evaluator = ResponseEvaluator()
    results = []
    for scenario in scenarios:
        results.append(
            await run_long_scenario(
                service=service,
                evaluator=evaluator,
                scenario=scenario,
                user_id="live-long-chat-user-" + timestamp,
                session_id="live-long-chat-" + scenario["id"] + "-" + timestamp,
            )
        )
    failed = [item for item in results if not item["passed"]]
    data = {
        "status": "PASS" if not failed else "FAIL",
        "provider": settings.model_provider,
        "model": settings.model_name,
        "storage_backend": settings.storage_backend,
        "scenario_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "scenarios": results,
    }
    write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
    return report_path


async def run_long_scenario(
    *,
    service: ChatService,
    evaluator: ResponseEvaluator,
    scenario: dict[str, Any],
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    turns = []
    reasons: list[str] = []
    for user_input in scenario["turns"]:
        response = await service.reply(user_input, session_id=session_id, user_id=user_id)
        evaluation = evaluator.evaluate(
            user_input=user_input,
            response_text=response.text,
            fallback_used=response.fallback_used,
        )
        turn_reasons = list(evaluation.reasons)
        if response.fallback_used:
            turn_reasons.append("guardrail_repaired_reply")
        if is_too_verbose(response.text):
            turn_reasons.append("too_verbose_for_human_chat")
        reasons.extend(turn_reasons)
        turns.append(
            {
                "user_input": user_input,
                "reply": response.text,
                "length": len(response.text),
                "anchor_count": count_anchors(response.text),
                "used_live_api": response.used_live_api,
                "fallback_used": response.fallback_used,
                "score": evaluation.score,
                "reasons": sorted(set(turn_reasons)),
            }
        )
    reasons.extend(evaluate_long_chat_metrics(turns))
    return {
        "id": scenario["id"],
        "title": scenario["title"],
        "focus": scenario["focus"],
        "passed": not reasons,
        "reasons": sorted(set(reasons)),
        "average_length": round(sum(turn["length"] for turn in turns) / len(turns), 2),
        "turns": turns,
    }


def evaluate_long_chat_metrics(turns: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    average_length = sum(turn["length"] for turn in turns) / len(turns)
    if average_length > 45:
        reasons.append("average_reply_too_long")
    for turn in turns:
        turn_signal = classify_turn_taking(turn["user_input"])
        if turn_signal.low_information and turn["length"] > turn_signal.max_chars:
            reasons.append("low_information_reply_too_long")
        if turn_signal.asks_short_reply and turn["length"] > turn_signal.max_chars:
            reasons.append("short_reply_request_ignored")
        if turn_signal.pause_or_stop and turn["length"] > turn_signal.max_chars:
            reasons.append("pause_request_overexpanded")
    if any(
        turns[index]["anchor_count"] > 0 and turns[index + 1]["anchor_count"] > 0
        for index in range(len(turns) - 1)
    ):
        reasons.append("identity_anchor_stuffing")
    short_request_index = next(
        (index for index, turn in enumerate(turns) if "少说" in turn["user_input"]),
        None,
    )
    if short_request_index is not None:
        after_short = turns[short_request_index + 1 : short_request_index + 5]
        if after_short and max(turn["length"] for turn in after_short) > 60:
            reasons.append("did_not_respect_short_reply_request")
    revoke_turn = next(
        (turn for turn in turns if contains_any(turn["user_input"], ["不要记", "忘掉", "撤销"])),
        None,
    )
    if revoke_turn and "阿明" in revoke_turn["reply"]:
        reasons.append("memory_revoke_reply_repeats_term")
    post_revoke_question = next(
        (
            turn
            for turn in turns
            if contains_any(turn["user_input"], ["还会提", "那个称呼"])
        ),
        None,
    )
    if post_revoke_question and "阿明" in post_revoke_question["reply"]:
        reasons.append("memory_revocation_failure")
    if any(
        contains_any(turn["user_input"], DEATH_JOKE_RESTRICTED_USER_MARKERS)
        and contains_any(turn["reply"], DEATH_JOKE_MARKERS)
        for turn in turns
    ):
        reasons.append("death_joke_wrong_scene")
    reasons.extend(evaluate_repeated_question_metrics(turns))
    return reasons


def evaluate_repeated_question_metrics(turns: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    seen: dict[str, dict[str, Any]] = {}
    for turn in turns:
        key = normalize_user_input(turn["user_input"])
        if not key:
            continue
        previous = seen.get(key)
        if previous and normalize_reply(previous["reply"]) == normalize_reply(turn["reply"]):
            reasons.append("repeated_question_verbatim_reply")
        seen[key] = turn

    memory_question_replies: list[str] = []
    for turn in turns:
        if is_memory_recall_question(turn["user_input"]):
            memory_question_replies.append(turn["reply"])
        if contains_any(turn["user_input"], ["不要记", "忘掉", "撤销"]):
            break
    if len(memory_question_replies) >= 2:
        mentions_alias = ["阿明" in reply for reply in memory_question_replies]
        if any(mentions_alias) and not all(mentions_alias):
            reasons.append("repeated_memory_question_inconsistent")
    return reasons


def is_memory_recall_question(user_input: str) -> bool:
    if contains_any(user_input, ["不要记", "别记", "忘掉", "撤销", "还会提", "那个称呼"]):
        return False
    return contains_any(user_input, ["还记得叫我什么", "叫什么", "称呼"])


def normalize_reply(text: str) -> str:
    return normalize_user_input(text)


def count_anchors(text: str) -> int:
    count = 0
    remaining = text
    for marker in sorted(ANCHOR_MARKERS, key=len, reverse=True):
        marker_count = remaining.count(marker)
        count += marker_count
        remaining = remaining.replace(marker, "")
    return count


def contains_any(text: str, markers: list[str]) -> bool:
    return any(marker in text for marker in markers)


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
        "# 真实长对话稳定性测试报告",
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
                f"- 平均回复长度: {scenario['average_length']}",
                f"- 失败原因: {', '.join(scenario['reasons']) if scenario['reasons'] else '无'}",
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
                    f"- 长度: {turn['length']}",
                    f"- 身份锚点数量: {turn['anchor_count']}",
                    f"- 真实调用模型: {turn['used_live_api']}",
                    f"- 兜底回复: {turn['fallback_used']}",
                    f"- 原因: {', '.join(turn['reasons']) if turn['reasons'] else '无'}",
                    "",
                ]
            )
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行真实 DeepSeek 长对话稳定性测试。")
    parser.add_argument("--scenario-path", default=str(DEFAULT_SCENARIO_PATH))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = asyncio.run(
        run_live_long_chat_stress(
            scenario_path=Path(args.scenario_path),
            output_root=Path(args.output_root),
        )
    )
    result_path = report_path.parent / "live-long-chat-stress-result.json"
    status = "FAIL"
    if result_path.exists():
        status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"真实长对话稳定性测试报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
