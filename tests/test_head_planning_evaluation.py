from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.head.evaluation import evaluate_planning_scenarios, load_planning_scenarios
from app.head.calibration import (
    evaluate_multi_reviewer_annotations,
    evaluate_pairwise_preferences,
    load_multi_reviewer_annotations,
    load_pairwise_preferences,
)
from scripts.evaluate_head_planning import run_evaluation


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = PROJECT_ROOT / "data" / "head_planning_scenarios.json"
PREFERENCE_PATH = PROJECT_ROOT / "data" / "head_planning_pairwise_preferences.json"
ANNOTATION_PATH = PROJECT_ROOT / "data" / "head_planning_multi_reviewer_annotations.json"


def test_head_planning_scenario_catalog_passes() -> None:
    scenarios = load_planning_scenarios(SCENARIO_PATH)
    result = evaluate_planning_scenarios(scenarios)

    assert len(scenarios) >= 20
    assert result["status"] == "PASS", [
        (item["id"], item["reasons"], item["selected_action"])
        for item in result["results"]
        if not item["passed"]
    ]
    assert result["selection_accuracy"] == 1.0
    assert result["complexity_accuracy"] == 1.0


def test_head_planning_report_contains_counterfactual_metrics(tmp_path: Path) -> None:
    report_path = run_evaluation(scenario_path=SCENARIO_PATH, output_root=tmp_path)
    result_path = report_path.with_name("head-planning-result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert report_path.exists()
    assert result["status"] == "PASS"
    assert "Counterfactual score gap" in report_path.read_text(encoding="utf-8")
    assert result["pairwise"]["pairwise_accuracy"] == 1.0
    assert result["multi_reviewer"]["fleiss_kappa"] >= 0.6


def test_pairwise_preferences_rank_the_preferred_action_higher() -> None:
    scenario_result = evaluate_planning_scenarios(load_planning_scenarios(SCENARIO_PATH))
    result = evaluate_pairwise_preferences(
        scenario_result["results"],
        load_pairwise_preferences(PREFERENCE_PATH),
    )

    assert result["preference_count"] >= 10
    assert result["status"] == "PASS", [
        (item["id"], item["reason"], item["margin"])
        for item in result["results"]
        if not item["passed"]
    ]


def test_multi_reviewer_agreement_and_consensus_alignment() -> None:
    scenario_result = evaluate_planning_scenarios(load_planning_scenarios(SCENARIO_PATH))
    result = evaluate_multi_reviewer_annotations(
        scenario_result["results"],
        load_multi_reviewer_annotations(ANNOTATION_PATH),
    )

    assert result["annotation_count"] == 10
    assert result["reviewer_count"] == 3
    assert result["unanimous_rate"] == 0.8
    assert result["fleiss_kappa"] >= 0.6
    assert result["planner_consensus_accuracy"] == 1.0
    assert result["status"] == "PASS"


def test_multi_reviewer_loader_rejects_duplicate_reviewers(tmp_path: Path) -> None:
    path = tmp_path / "invalid-annotations.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "scenario_id": "casual-direct",
                    "action_a": "answer",
                    "action_b": "clarify",
                    "judgments": [
                        {"reviewer_id": "same", "preferred_action": "answer"},
                        {"reviewer_id": "same", "preferred_action": "clarify"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate reviewer"):
        load_multi_reviewer_annotations(path)


def test_invalid_planning_catalog_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps([{"id": "missing-fields"}]), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid planning scenario"):
        load_planning_scenarios(path)
