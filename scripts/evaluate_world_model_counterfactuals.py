from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import PROJECT_ROOT
from app.head.contracts import CausalHypothesis, WorldEvent
from app.head.world_simulation import (
    CounterfactualTrial,
    TRIAL_STATUS_EXPIRED,
    resolve_counterfactual_trials,
)

DEFAULT_SCENARIOS = PROJECT_ROOT / "data" / "world_model_counterfactual_scenarios.json"


def _event(item: dict[str, Any]) -> WorldEvent:
    return WorldEvent(
        event_id=str(item["event_id"]),
        event_type=str(item["event_type"]),
        actor_ids=tuple(str(value) for value in item["actor_ids"]),
        occurred_at=str(item["occurred_at"]),
        source_id=str(item["source_id"]),
        summary=str(item["summary"]),
        confidence=float(item["confidence"]),
    )


def _hypothesis(item: dict[str, Any]) -> CausalHypothesis:
    return CausalHypothesis(
        str(item["id"]),
        str(item["cause_event_id"]),
        str(item["effect_event_id"]),
        str(item["rationale"]),
        float(item["confidence"]),
        tuple(str(value) for value in item.get("evidence_ids", [])),
        bool(item.get("confirmed", False)),
    )


def _trial(item: dict[str, Any]) -> CounterfactualTrial:
    return CounterfactualTrial(
        trial_id=str(item["id"]),
        hypothesis_id=str(item["hypothesis_id"]),
        expected_event_type=str(item["expected_event_type"]),
        counter_event_types=tuple(str(value) for value in item.get("counter_event_types", [])),
        created_at=str(item["created_at"]),
        horizon_days=int(item.get("horizon_days", 7)),
    )


def evaluate_scenarios(document: dict[str, Any], *, now: dt.datetime | None = None) -> dict[str, Any]:
    current = _aware_parse(str(document["now"])) if now is None else _aware_parse(now.isoformat())
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0
    for scenario in document["scenarios"]:
        hypotheses = tuple(_hypothesis(item) for item in scenario["hypotheses"])
        trials = tuple(_trial(item) for item in scenario["trials"])
        events = tuple(_event(item) for item in scenario["events"])
        resolution = resolve_counterfactual_trials(hypotheses, trials, events, now=current)
        expect = scenario["expect"]
        checks = {
            "supported": sorted(resolution.supported_hypothesis_ids)
            == sorted(expect.get("supported", [])),
            "refuted": sorted(resolution.refuted_hypothesis_ids)
            == sorted(expect.get("refuted", [])),
            "confirmed": sorted(
                hypothesis.hypothesis_id
                for hypothesis in resolution.hypotheses
                if hypothesis.confirmed
            )
            == sorted(expect.get("confirmed", [])),
            "expired": sorted(
                trial.trial_id for trial in resolution.trials if trial.status == TRIAL_STATUS_EXPIRED
            )
            == sorted(expect.get("expired", [])),
        }
        ok = all(checks.values())
        passed += int(ok)
        failed += int(not ok)
        results.append(
            {
                "id": scenario["id"],
                "passed": ok,
                "checks": checks,
            }
        )
    return {
        "status": "PASS" if failed == 0 else "FAIL",
        "passed": passed,
        "failed": failed,
        "margin": round(passed / max(1, passed + failed), 4),
        "scenarios": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate counterfactual trial scenarios offline.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    document = json.loads(args.scenarios.read_text(encoding="utf-8"))
    result = evaluate_scenarios(document)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "counterfactual-eval-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        lines = [
            "# 反事实推演离线评估报告",
            "",
            f"- 状态: {result['status']}",
            f"- 通过: {result['passed']}/{result['passed'] + result['failed']}",
            f"- margin: {result['margin']}",
        ]
        (args.output_dir / "counterfactual-eval-report.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return 0 if result["status"] == "PASS" else 1


def _aware_parse(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)


if __name__ == "__main__":
    raise SystemExit(main())
