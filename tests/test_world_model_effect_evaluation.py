from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_world_model_effects import run_evaluation


def test_world_model_effect_evaluation_reports_demonstrated_level_and_gaps(
    tmp_path: Path,
) -> None:
    report_path = run_evaluation(output_root=tmp_path)
    result_path = report_path.with_name("world-model-effects-result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    scenarios = {item["id"]: item for item in result["scenarios"]}

    assert result["status"] == "FAIL"
    assert result["demonstrated_level"] == "L1"
    assert result["required_scenario_failures"] == 1
    assert result["required_scenario_gaps"] == 1
    assert scenarios["relation_conflict_guard"]["status"] == "PASS"
    assert scenarios["head_decision_world_state"]["status"] == "FAIL"
    assert scenarios["chat_world_guard_blocks_unsupported_claims"]["status"] == "PASS"
    assert scenarios["chat_prompt_uses_persisted_world_graph"]["status"] == "PASS"
    assert scenarios["weather_fact_same_turn_ingestion"]["status"] == "PASS"
    assert scenarios["web_weather_fact_cross_turn_persistence"]["status"] == "GAP"
    assert scenarios["automatic_world_graph_growth"]["status"] == "GAP"
    assert scenarios["world_dynamics_prediction"]["status"] == "GAP"
    report_text = report_path.read_text(encoding="utf-8")
    assert "当前可证明等级：L1" in report_text
    assert "当前 L1 结论" in report_text
    assert "当前 L2 结论" not in report_text


def test_world_model_effect_evaluation_does_not_write_runtime_storage_outside_report(
    tmp_path: Path,
) -> None:
    report_path = run_evaluation(output_root=tmp_path)

    assert sorted(path.name for path in report_path.parent.iterdir()) == [
        "world-model-effects-report.md",
        "world-model-effects-result.json",
    ]
