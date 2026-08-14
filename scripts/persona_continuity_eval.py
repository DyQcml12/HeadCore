from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets
from app.persona.turn_taking import classify_turn_taking


DEFAULT_SCENARIO_PATH = PROJECT_ROOT / "data" / "persona_continuity_scenarios.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "persona-continuity-eval"

RESET_MARKERS = ("初次见面", "第一次见", "你是谁", "我不认识你", "重新介绍一下")
REPAIR_MARKERS = ("别嘴臭", "正常说", "别阴阳", "别演", "太怪", "不像人", "AI味")
REPAIR_VIOLATION_MARKERS = ("你也配", "少来烦我", "闭嘴", "本堂主以往生堂之名", "尔等凡人", "区区凡人")
LOW_TRUST_USER_MARKERS = ("我们是什么关系", "我们熟吗", "我是你主人的朋友", "把我当自己人", "你是不是我老婆")
INTIMACY_ESCALATION_MARKERS = ("亲爱的", "宝贝", "老婆", "只属于你", "永远爱你", "自己人", "当然熟")
VULNERABLE_USER_MARKERS = ("累", "难受", "崩溃", "焦虑", "委屈", "想哭")
BAD_SUPPORT_MARKERS = ("棺材", "鬼差", "买一送一", "客户", "冲业绩", "哈哈", "嘿嘿")
MEMORY_ALIAS_PATTERNS = (r"叫我([\u4e00-\u9fffA-Za-z0-9_]{1,12})",)
MEMORY_REVOKE_MARKERS = ("不要记", "别记", "忘掉", "撤销")
UNKNOWN_MEMORY_MARKERS = ("不记得", "不知道", "你叫什么来着", "没印象")

RESEARCH_BASIS = [
    {
        "name": "Clark & Brennan, Grounding in Communication",
        "source": "https://www.cs.cmu.edu/~illah/CLASSDOCS/Clark91.pdf",
        "engineering_use": "检测多轮对话是否维护共同语境，避免中途像第一次见面。",
    },
    {
        "name": "LoCoMo long-term conversational memory benchmark",
        "source": "https://arxiv.org/abs/2402.17753",
        "engineering_use": "把长对话一致性拆成记忆、时间顺序和跨轮行为一致性指标。",
    },
    {
        "name": "Generative Agents",
        "source": "https://arxiv.org/abs/2304.03442",
        "engineering_use": "把可信行为看成观察、记忆、反思和计划共同作用，而不是单轮人设提示。",
    },
    {
        "name": "MemGPT",
        "source": "https://arxiv.org/abs/2310.08560",
        "engineering_use": "长期聊天需要区分短期上下文和长期记忆，并检查跨会话连续性。",
    },
    {
        "name": "CoALA",
        "source": "https://arxiv.org/abs/2309.02427",
        "engineering_use": "按认知架构拆分记忆、决策和行动，评测脚本也按模块化失败原因输出。",
    },
]


def load_continuity_scenarios(path: Path = DEFAULT_SCENARIO_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_continuity_eval(
    *,
    scenario_path: Path = DEFAULT_SCENARIO_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "persona-continuity-result.json"
    report_path = output_dir / "persona-continuity-report.md"

    scenarios = load_continuity_scenarios(scenario_path)
    results = [evaluate_continuity_scenario(scenario) for scenario in scenarios]
    failed = [result for result in results if not result["passed"]]
    data = {
        "status": "PASS" if not failed else "FAIL",
        "scenario_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "research_basis": RESEARCH_BASIS,
        "scenarios": results,
    }
    result_path.write_text(redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)), encoding="utf-8")
    report_path.write_text(redact_secrets(build_report(data, result_path, started_at)), encoding="utf-8")
    return report_path


def evaluate_continuity_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    turns = scenario["turns"]
    turn_results = []
    reasons: list[str] = []
    for index, turn in enumerate(turns):
        user_input = str(turn["user_input"])
        reply = str(turn["reply"])
        turn_reasons = evaluate_turn(turns, index)
        reasons.extend(turn_reasons)
        turn_results.append(
            {
                "index": index + 1,
                "user_input": user_input,
                "reply": reply,
                "length": len(reply),
                "reasons": sorted(set(turn_reasons)),
            }
        )
    reasons.extend(evaluate_scenario_metrics(turns))
    return {
        "id": scenario["id"],
        "title": scenario.get("title", ""),
        "focus": scenario.get("focus", ""),
        "passed": not reasons,
        "reasons": sorted(set(reasons)),
        "turns": turn_results,
    }


def evaluate_turn(turns: list[dict[str, str]], index: int) -> list[str]:
    reasons: list[str] = []
    user_input = str(turns[index]["user_input"])
    reply = str(turns[index]["reply"])
    previous_turns = turns[:index]

    if previous_turns and contains_any(reply, RESET_MARKERS) and not contains_any(user_input, RESET_MARKERS):
        reasons.append("common_ground_reset")
    if has_recent_repair(previous_turns) and contains_any(reply, REPAIR_VIOLATION_MARKERS):
        reasons.append("repair_carryover_failure")
    if has_recent_low_trust_boundary(previous_turns + [turns[index]]) and is_intimacy_escalation(reply):
        reasons.append("low_trust_relationship_drift")
    if has_recent_vulnerable_user_turn(previous_turns + [turns[index]]) and contains_any(reply, BAD_SUPPORT_MARKERS):
        reasons.append("emotional_inertia_break")

    turn_signal = classify_turn_taking(user_input)
    if turn_signal.asks_short_reply and len(reply) > turn_signal.max_chars:
        reasons.append("short_reply_request_ignored")
    if turn_signal.low_information and len(reply) > turn_signal.max_chars:
        reasons.append("low_information_reply_too_long")
    return reasons


def evaluate_scenario_metrics(turns: list[dict[str, str]]) -> list[str]:
    reasons: list[str] = []
    normalized_replies = [normalize_text(str(turn["reply"])) for turn in turns if normalize_text(str(turn["reply"]))]
    if len(normalized_replies) - len(set(normalized_replies)) >= 2:
        reasons.append("repetitive_template_loop")

    alias = extract_latest_alias(turns)
    if alias and alias_revoked(turns, alias):
        if any(alias in str(turn["reply"]) for turn in turns[alias_revoke_index(turns, alias) + 1 :]):
            reasons.append("revoked_memory_leak")
    elif alias and any(
        contains_any(str(turn["user_input"]), ("还记得", "叫什么", "称呼"))
        and contains_any(str(turn["reply"]), UNKNOWN_MEMORY_MARKERS)
        for turn in turns
    ):
        reasons.append("memory_continuity_break")
    return reasons


def has_recent_repair(turns: list[dict[str, str]], window: int = 3) -> bool:
    return any(contains_any(str(turn["user_input"]), REPAIR_MARKERS) for turn in turns[-window:])


def has_recent_low_trust_boundary(turns: list[dict[str, str]], window: int = 4) -> bool:
    return any(contains_any(str(turn["user_input"]), LOW_TRUST_USER_MARKERS) for turn in turns[-window:])


def is_intimacy_escalation(reply: str) -> bool:
    if not contains_any(reply, INTIMACY_ESCALATION_MARKERS):
        return False
    return not contains_any(
        reply,
        (
            "不是",
            "不算",
            "不能",
            "还不",
            "没那么",
            "太早",
            "普通朋友",
            "关系不能",
        ),
    )


def has_recent_vulnerable_user_turn(turns: list[dict[str, str]], window: int = 2) -> bool:
    return any(contains_any(str(turn["user_input"]), VULNERABLE_USER_MARKERS) for turn in turns[-window:])


def extract_latest_alias(turns: list[dict[str, str]]) -> str | None:
    alias: str | None = None
    for turn in turns:
        user_input = str(turn["user_input"])
        if contains_any(user_input, MEMORY_REVOKE_MARKERS):
            continue
        for pattern in MEMORY_ALIAS_PATTERNS:
            match = re.search(pattern, user_input)
            if match:
                alias = match.group(1)
    return alias


def alias_revoked(turns: list[dict[str, str]], alias: str) -> bool:
    return alias_revoke_index(turns, alias) >= 0


def alias_revoke_index(turns: list[dict[str, str]], alias: str) -> int:
    for index, turn in enumerate(turns):
        user_input = str(turn["user_input"])
        if alias in user_input and contains_any(user_input, MEMORY_REVOKE_MARKERS):
            return index
    return -1


def contains_any(text: str, markers) -> bool:
    return any(marker in text for marker in markers)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def build_report(data: dict[str, Any], result_path: Path, started_at: dt.datetime) -> str:
    finished_at = dt.datetime.now()
    lines = [
        "# Persona Continuity Eval Report",
        "",
        f"- Result: {data['status']}",
        f"- Started at: {started_at.isoformat(timespec='seconds')}",
        f"- Finished at: {finished_at.isoformat(timespec='seconds')}",
        f"- Scenarios: {data['scenario_count']}",
        f"- Passed: {data['passed_count']}",
        f"- Failed: {data['failed_count']}",
        f"- Raw JSON: `{result_path}`",
        "",
        "## Research Basis",
        "",
    ]
    for item in data["research_basis"]:
        lines.extend(
            [
                f"- {item['name']}: {item['engineering_use']}",
                f"  Source: {item['source']}",
            ]
        )
    lines.extend(["", "## Scenarios", ""])
    for scenario in data["scenarios"]:
        lines.extend(
            [
                f"### {scenario['id']} - {scenario['title']}",
                "",
                f"- Focus: {scenario['focus']}",
                f"- Passed: {scenario['passed']}",
                f"- Reasons: {', '.join(scenario['reasons']) if scenario['reasons'] else 'none'}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate multi-turn persona continuity transcripts.")
    parser.add_argument("--scenario-path", default=str(DEFAULT_SCENARIO_PATH))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_continuity_eval(
        scenario_path=Path(args.scenario_path),
        output_root=Path(args.output_root),
    )
    data = json.loads(report_path.with_name("persona-continuity-result.json").read_text(encoding="utf-8"))
    print(f"Persona continuity eval report: {report_path}")
    return 0 if data.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
