from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.head.blind_review import build_blind_review_package, evaluate_blind_reviews, write_review_csv


def _scenario_results() -> list[dict[str, object]]:
    return [
        {
            "id": "scene-1",
            "user_input": "这个应该怎么继续？",
            "candidates": [
                {"action": "clarify", "objective": "先确认缺失对象", "score": {"total": 0.8}},
                {"action": "answer", "objective": "根据现有信息直接回答", "score": {"total": 0.4}},
            ],
        },
        {
            "id": "scene-2",
            "user_input": "继续完成接口。",
            "candidates": [
                {"action": "continue_task", "objective": "继续推进明确任务", "score": {"total": 0.9}},
                {"action": "clarify", "objective": "再次询问任务对象", "score": {"total": 0.2}},
            ],
        },
    ]


def _preferences() -> list[dict[str, str]]:
    return [
        {"id": "p1", "scenario_id": "scene-1", "preferred_action": "clarify", "rejected_action": "answer"},
        {"id": "p2", "scenario_id": "scene-2", "preferred_action": "continue_task", "rejected_action": "clarify"},
    ]


def _submission(package: dict[str, object], reviewer: str, choices: list[str]) -> list[dict[str, str]]:
    items = package["public_items"]
    assert isinstance(items, list)
    return [
        {
            **item,
            "reviewer_id": reviewer,
            "selected_option": choice,
            "confidence": "4",
            "notes": "",
        }
        for item, choice in zip(items, choices)
    ]


def test_blind_package_is_deterministic_and_hides_internal_decision() -> None:
    first = build_blind_review_package(_scenario_results(), _preferences(), seed="stable")
    second = build_blind_review_package(_scenario_results(), _preferences(), seed="stable")

    assert first == second
    public_text = str(first["public_items"])
    assert "headcore_preferred_action" not in public_text
    assert "score" not in public_text
    assert "preferred_action" not in public_text


def test_review_csv_contains_only_public_fields(tmp_path: Path) -> None:
    package = build_blind_review_package(_scenario_results(), _preferences())
    path = tmp_path / "review.csv"
    write_review_csv(package, path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert "headcore_preferred_action" not in rows[0]
    assert rows[0]["selected_option"] == ""


def test_three_reviewer_import_calculates_consensus_and_win_rate() -> None:
    package = build_blind_review_package(_scenario_results(), _preferences(), seed="stable")
    preferred_choices = [
        "A" if mapping["option_a_action"] == mapping["headcore_preferred_action"] else "B"
        for mapping in package["mappings"]
    ]
    opposite = ["B" if choice == "A" else "A" for choice in preferred_choices]
    result = evaluate_blind_reviews(
        package,
        [
            (Path("r1.csv"), _submission(package, "r1", preferred_choices)),
            (Path("r2.csv"), _submission(package, "r2", preferred_choices)),
            (Path("r3.csv"), _submission(package, "r3", opposite)),
        ],
    )

    assert result["reviewer_count"] == 3
    assert result["headcore_consensus_alignment"] == 1.0
    assert result["headcore_vote_win_rate"] == pytest.approx(2 / 3, abs=0.0001)
    assert result["tie_count"] == 0


def test_duplicate_reviewer_and_invalid_or_incomplete_rows_are_rejected() -> None:
    package = build_blind_review_package(_scenario_results(), _preferences())
    valid = _submission(package, "same", ["A", "B"])
    with pytest.raises(ValueError, match="duplicate reviewer"):
        evaluate_blind_reviews(package, [(Path("a.csv"), valid), (Path("b.csv"), valid)])
    invalid = _submission(package, "r2", ["X", "B"])
    with pytest.raises(ValueError, match="invalid selected_option"):
        evaluate_blind_reviews(package, [(Path("a.csv"), valid), (Path("b.csv"), invalid)])
    with pytest.raises(ValueError, match="incomplete or duplicated"):
        evaluate_blind_reviews(package, [(Path("a.csv"), valid), (Path("b.csv"), _submission(package, "r2", ["A"])[:1])])


def test_even_reviewer_tie_is_reported_without_false_alignment() -> None:
    package = build_blind_review_package(_scenario_results(), _preferences())
    result = evaluate_blind_reviews(
        package,
        [
            (Path("a.csv"), _submission(package, "r1", ["A", "A"])),
            (Path("b.csv"), _submission(package, "r2", ["B", "B"])),
        ],
    )
    assert result["tie_count"] == 2
    assert result["headcore_consensus_alignment"] is None
