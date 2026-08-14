from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.security import redact_secrets
from app.head.calibration import (
    evaluate_multi_reviewer_annotations,
    evaluate_pairwise_preferences,
    load_multi_reviewer_annotations,
    load_pairwise_preferences,
)
from app.head.evaluation import evaluate_planning_scenarios, load_planning_scenarios


DEFAULT_SCENARIOS = PROJECT_ROOT / "data" / "head_planning_scenarios.json"
DEFAULT_PREFERENCES = PROJECT_ROOT / "data" / "head_planning_pairwise_preferences.json"
DEFAULT_ANNOTATIONS = PROJECT_ROOT / "data" / "head_planning_multi_reviewer_annotations.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "head-planning-eval"


def run_evaluation(
    *,
    scenario_path: Path,
    output_root: Path,
    preference_path: Path = DEFAULT_PREFERENCES,
    annotation_path: Path = DEFAULT_ANNOTATIONS,
) -> Path:
    started_at = dt.datetime.now()
    output_dir = output_root / started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = evaluate_planning_scenarios(load_planning_scenarios(scenario_path))
    pairwise = evaluate_pairwise_preferences(
        result["results"],
        load_pairwise_preferences(preference_path),
    )
    result["pairwise"] = pairwise
    reviewers = evaluate_multi_reviewer_annotations(
        result["results"],
        load_multi_reviewer_annotations(annotation_path),
    )
    result["multi_reviewer"] = reviewers
    if pairwise["status"] != "PASS" or reviewers["status"] != "PASS":
        result["status"] = "FAIL"
    result_path = output_dir / "head-planning-result.json"
    report_path = output_dir / "head-planning-report.md"
    result_path.write_text(
        redact_secrets(json.dumps(result, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    report_path.write_text(
        redact_secrets(_build_report(result, result_path, started_at)),
        encoding="utf-8",
    )
    return report_path


def _build_report(result: dict[str, Any], result_path: Path, started_at: dt.datetime) -> str:
    lines = [
        "# HeadCore Planning Offline Evaluation",
        "",
        f"- Result: {result['status']}",
        f"- Started at: {started_at.isoformat(timespec='seconds')}",
        f"- Scenarios: {result['scenario_count']}",
        f"- Passed: {result['passed_count']}",
        f"- Failed: {result['failed_count']}",
        f"- Selection accuracy: {result['selection_accuracy']:.2%}",
        f"- Complexity accuracy: {result['complexity_accuracy']:.2%}",
        f"- Average selected risk: {result['average_selected_risk']:.4f}",
        f"- Pairwise accuracy: {result['pairwise']['pairwise_accuracy']:.2%}",
        f"- Average preference margin: {result['pairwise']['average_margin']:.4f}",
        f"- Multi-reviewer raw agreement: {result['multi_reviewer']['raw_agreement']:.2%}",
        f"- Unanimous rate: {result['multi_reviewer']['unanimous_rate']:.2%}",
        f"- Fleiss' Kappa: {result['multi_reviewer']['fleiss_kappa']:.4f}",
        f"- Planner / reviewer consensus accuracy: {result['multi_reviewer']['planner_consensus_accuracy']:.2%}",
        f"- Raw JSON: `{result_path}`",
        "",
        "## Scenarios",
        "",
    ]
    for item in result["results"]:
        lines.extend(
            [
                f"### {item['id']} - {item['title']}",
                "",
                f"- Passed: {item['passed']}",
                f"- Expected / selected: {item['expected_action']} / {item['selected_action']}",
                f"- Complex expected / actual: {item['expected_complex']} / {item['actual_complex']}",
                f"- Candidate count: {item['candidate_count']}",
                f"- Selection margin: {item['selection_margin']}",
                f"- Counterfactual score gap: {item['counterfactual_score_gap']}",
                f"- Reasons: {', '.join(item['reasons']) if item['reasons'] else 'none'}",
                "",
            ]
        )
    lines.extend(["## Pairwise Preferences", ""])
    for item in result["pairwise"]["results"]:
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Scenario: {item['scenario_id']}",
                f"- Preferred / rejected: {item['preferred_action']} / {item['rejected_action']}",
                f"- Margin / minimum: {item['margin']} / {item['minimum_margin']}",
                f"- Passed: {item['passed']}",
                f"- Reason: {item['reason']}",
                "",
            ]
        )
    lines.extend(["## Multi-reviewer Agreement", ""])
    for item in result["multi_reviewer"]["results"]:
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Scenario: {item['scenario_id']}",
                f"- Vote counts: {item['vote_counts']}",
                f"- Agreement: {item['agreement']:.2%}",
                f"- Consensus / planner: {item['consensus_action']} / {item['planner_preferred_action']}",
                f"- Aligned: {item['planner_aligned']}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deterministic HeadCore action planning.")
    parser.add_argument("--scenario-path", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--preference-path", type=Path, default=DEFAULT_PREFERENCES)
    parser.add_argument("--annotation-path", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_evaluation(
        scenario_path=args.scenario_path,
        preference_path=args.preference_path,
        annotation_path=args.annotation_path,
        output_root=args.output_root,
    )
    result = json.loads(report_path.with_name("head-planning-result.json").read_text(encoding="utf-8"))
    print(f"HeadCore planning report: {report_path}")
    print(f"Result: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
