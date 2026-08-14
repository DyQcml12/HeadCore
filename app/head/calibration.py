from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_pairwise_preferences(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("pairwise preference file must contain a JSON list")
    required = {"id", "scenario_id", "preferred_action", "rejected_action"}
    for index, preference in enumerate(payload):
        if not isinstance(preference, dict) or not required.issubset(preference):
            raise ValueError(f"invalid pairwise preference at index {index}")
    return payload


def load_multi_reviewer_annotations(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("multi-reviewer annotation file must contain a JSON list")
    required = {"id", "scenario_id", "action_a", "action_b", "judgments"}
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"invalid multi-reviewer annotation at index {index}")
        judgments = item["judgments"]
        if not isinstance(judgments, list) or len(judgments) < 2:
            raise ValueError(f"multi-reviewer annotation {item['id']} needs at least two judgments")
        reviewer_ids = [judgment.get("reviewer_id") for judgment in judgments]
        votes = [judgment.get("preferred_action") for judgment in judgments]
        if len(set(reviewer_ids)) != len(reviewer_ids):
            raise ValueError(f"duplicate reviewer in annotation {item['id']}")
        if any(vote not in {item["action_a"], item["action_b"]} for vote in votes):
            raise ValueError(f"invalid vote in annotation {item['id']}")
    return payload


def evaluate_pairwise_preferences(
    scenario_results: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
) -> dict[str, Any]:
    scenarios = {str(item["id"]): item for item in scenario_results}
    results = []
    for preference in preferences:
        scenario = scenarios.get(str(preference["scenario_id"]))
        if scenario is None:
            results.append(_missing_result(preference, "scenario_missing"))
            continue
        candidates = scenario.get("candidates", [])
        preferred_score = _best_action_score(candidates, str(preference["preferred_action"]))
        rejected_score = _best_action_score(candidates, str(preference["rejected_action"]))
        if preferred_score is None or rejected_score is None:
            results.append(_missing_result(preference, "candidate_missing"))
            continue
        margin = round(preferred_score - rejected_score, 4)
        minimum = float(preference.get("minimum_margin", 0.0))
        results.append(
            {
                "id": str(preference["id"]),
                "scenario_id": str(preference["scenario_id"]),
                "preferred_action": str(preference["preferred_action"]),
                "rejected_action": str(preference["rejected_action"]),
                "preferred_score": preferred_score,
                "rejected_score": rejected_score,
                "margin": margin,
                "minimum_margin": minimum,
                "passed": margin > minimum,
                "reason": "preferred_ranked_higher" if margin > minimum else "preference_misranked",
            }
        )
    passed = sum(1 for item in results if item["passed"])
    return {
        "status": "PASS" if passed == len(results) else "FAIL",
        "preference_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "pairwise_accuracy": round(passed / len(results), 4) if results else 0.0,
        "average_margin": round(
            sum(float(item.get("margin") or 0.0) for item in results) / max(len(results), 1), 4
        ),
        "results": results,
    }


def evaluate_multi_reviewer_annotations(
    scenario_results: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    *,
    minimum_kappa: float = 0.6,
) -> dict[str, Any]:
    scenarios = {str(item["id"]): item for item in scenario_results}
    results: list[dict[str, Any]] = []
    vote_counts: list[dict[str, int]] = []
    unanimous = 0
    aligned = 0
    for item in annotations:
        votes = [str(value["preferred_action"]) for value in item["judgments"]]
        counts = {action: votes.count(action) for action in sorted(set(votes))}
        vote_counts.append(counts)
        ranking = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        tied = len(ranking) > 1 and ranking[0][1] == ranking[1][1]
        consensus = None if tied else ranking[0][0]
        if len(counts) == 1:
            unanimous += 1
        scenario = scenarios.get(str(item["scenario_id"]))
        action_a_score = _best_action_score(scenario.get("candidates", []), str(item["action_a"])) if scenario else None
        action_b_score = _best_action_score(scenario.get("candidates", []), str(item["action_b"])) if scenario else None
        planner_preferred = None
        if action_a_score is not None and action_b_score is not None:
            planner_preferred = str(item["action_a"]) if action_a_score > action_b_score else str(item["action_b"])
        planner_aligned = consensus is not None and planner_preferred == consensus
        aligned += int(planner_aligned)
        results.append(
            {
                "id": str(item["id"]),
                "scenario_id": str(item["scenario_id"]),
                "reviewer_count": len(votes),
                "vote_counts": counts,
                "agreement": round(sum(count * (count - 1) for count in counts.values()) / (len(votes) * (len(votes) - 1)), 4),
                "consensus_action": consensus,
                "planner_preferred_action": planner_preferred,
                "planner_aligned": planner_aligned,
                "reason": "aligned" if planner_aligned else "tie_or_planner_disagreement",
            }
        )
    kappa = _fleiss_kappa(vote_counts)
    count = len(results)
    alignment = round(aligned / count, 4) if count else 0.0
    status = "PASS" if kappa >= minimum_kappa and aligned == count else "FAIL"
    return {
        "status": status,
        "annotation_count": count,
        "reviewer_count": len({str(j["reviewer_id"]) for item in annotations for j in item["judgments"]}),
        "unanimous_rate": round(unanimous / count, 4) if count else 0.0,
        "raw_agreement": round(sum(item["agreement"] for item in results) / max(count, 1), 4),
        "fleiss_kappa": kappa,
        "minimum_kappa": minimum_kappa,
        "planner_consensus_accuracy": alignment,
        "results": results,
    }


def _fleiss_kappa(vote_counts: list[dict[str, int]]) -> float:
    if not vote_counts:
        return 0.0
    raters = sum(vote_counts[0].values())
    if raters < 2 or any(sum(counts.values()) != raters for counts in vote_counts):
        raise ValueError("Fleiss kappa requires the same number of raters for every item")
    categories = sorted({category for counts in vote_counts for category in counts})
    item_agreement = [
        sum(counts.get(category, 0) ** 2 for category in categories) - raters
        for counts in vote_counts
    ]
    p_bar = sum(value / (raters * (raters - 1)) for value in item_agreement) / len(vote_counts)
    total_votes = len(vote_counts) * raters
    category_proportions = [
        sum(counts.get(category, 0) for counts in vote_counts) / total_votes
        for category in categories
    ]
    expected = sum(value * value for value in category_proportions)
    if expected >= 1.0:
        return 1.0
    return round((p_bar - expected) / (1.0 - expected), 4)


def _best_action_score(candidates: list[dict[str, Any]], action: str) -> float | None:
    scores = [float(item["score"]["total"]) for item in candidates if item.get("action") == action]
    return max(scores) if scores else None


def _missing_result(preference: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "id": str(preference["id"]),
        "scenario_id": str(preference["scenario_id"]),
        "preferred_action": str(preference["preferred_action"]),
        "rejected_action": str(preference["rejected_action"]),
        "preferred_score": None,
        "rejected_score": None,
        "margin": None,
        "minimum_margin": float(preference.get("minimum_margin", 0.0)),
        "passed": False,
        "reason": reason,
    }
