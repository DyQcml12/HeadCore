from __future__ import annotations

import json
from pathlib import Path

from scripts.stress_world_model import STRESS_PROFILES, run_stress


def test_smoke_stress_exercises_all_world_model_paths(tmp_path: Path) -> None:
    report_path = run_stress(profile="smoke", output_root=tmp_path, seed=20260729)
    result_path = report_path.with_name("world-model-stress-result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["status"] == "PASS"
    assert result["profile"] == "smoke"
    assert result["seed"] == 20260729
    assert result["config"] == STRESS_PROFILES["smoke"]
    assert result["external_calls"] == 0
    assert result["totals"]["errors"] == 0
    assert result["totals"]["integrity_errors"] == 0
    assert result["totals"]["semantic_errors"] == 0

    phases = result["phases"]
    assert set(phases) == {
        "world_graph",
        "head_decision",
        "persistence",
        "corruption_recovery",
        "chat_service",
    }
    assert phases["world_graph"]["operations"] == STRESS_PROFILES["smoke"][
        "graph_iterations"
    ]
    assert phases["head_decision"]["operations"] == STRESS_PROFILES["smoke"][
        "decision_iterations"
    ]
    assert phases["persistence"]["users_verified"] == STRESS_PROFILES["smoke"][
        "persistence_users"
    ]
    assert phases["chat_service"]["operations"] == STRESS_PROFILES["smoke"][
        "chat_requests"
    ]
    assert phases["chat_service"]["provider_calls"] > 0
    assert phases["chat_service"]["provider_calls"] < phases["chat_service"][
        "operations"
    ]
    assert phases["chat_service"]["world_guard_responses"] > 0

    report_text = report_path.read_text(encoding="utf-8")
    assert "HeadCore World Model Stress Report" in report_text
    assert "No real network, model, database, camera, or user-data call was made." in report_text


def test_stress_writes_only_report_artifacts_to_output_root(tmp_path: Path) -> None:
    report_path = run_stress(profile="smoke", output_root=tmp_path, seed=7)

    assert report_path.parent.parent == tmp_path
    assert sorted(path.name for path in report_path.parent.iterdir()) == [
        "world-model-stress-report.md",
        "world-model-stress-result.json",
    ]
