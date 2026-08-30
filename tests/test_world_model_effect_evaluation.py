from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_world_model_effects import run_evaluation


def test_world_model_effect_evaluation_reports_all_supported_scenarios(
    tmp_path: Path,
) -> None:
    report_path = run_evaluation(output_root=tmp_path)
    result_path = report_path.with_name("world-model-effects-result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    scenarios = {item["id"]: item for item in result["scenarios"]}

    assert result["status"] == "PASS"
    assert result["demonstrated_level"] == "L2"
    assert result["required_scenario_failures"] == 0
    assert result["required_scenario_gaps"] == 0
    assert result["gap_count"] == 0
    for scenario_id in (
        "relation_conflict_guard",
        "head_decision_world_state",
        "chat_world_guard_blocks_unsupported_claims",
        "chat_prompt_uses_persisted_world_graph",
        "weather_fact_same_turn_ingestion",
        "web_weather_fact_cross_turn_persistence",
        "automatic_world_graph_growth",
        "world_dynamics_prediction",
    ):
        assert scenarios[scenario_id]["status"] == "PASS"
    assert "L2" in report_path.read_text(encoding="utf-8")


def test_world_model_effect_evaluation_does_not_write_runtime_storage_outside_report(
    tmp_path: Path,
) -> None:
    report_path = run_evaluation(output_root=tmp_path)

    assert sorted(path.name for path in report_path.parent.iterdir()) == [
        "world-model-effects-report.md",
        "world-model-effects-result.json",
    ]
