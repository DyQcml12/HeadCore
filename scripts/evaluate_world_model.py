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
from app.head.contracts import (
    CausalHypothesis,
    CognitiveFact,
    CognitiveFactKind,
    CognitiveFactSourceKind,
    CognitiveFactStatus,
    WorldEntity,
    WorldEvent,
    WorldRelation,
)
from app.head.cognitive_facts import project_cognitive_fact_uncertainties, project_cognitive_facts, resolve_cognitive_facts
from app.head.world_calibration import calibrate_facts_with_observations
from app.head.world_model import build_head_world_model, project_head_world_model
from app.head.world_simulation import CounterfactualTrial, resolve_counterfactual_trials

DEFAULT_CASES = PROJECT_ROOT / "data" / "world_model_evaluation_cases.json"

EVAL_DISCLAIMER = (
    "本评估只验证世界模型行为可预测、来源可追溯；不构成对 AGI、意识或人类等同思维的主张。"
)


def _entity(item: dict[str, Any]) -> WorldEntity:
    return WorldEntity(str(item["entity_id"]), str(item["entity_type"]), str(item["name"]))


def _relation(item: dict[str, Any]) -> WorldRelation:
    return WorldRelation(
        relation_id=str(item["relation_id"]),
        subject_id=str(item["subject_id"]),
        predicate=str(item["predicate"]),
        object_id=str(item["object_id"]),
        source_id=str(item["source_id"]),
        valid_from=str(item["valid_from"]),
        valid_until=item.get("valid_until"),
        confidence=float(item["confidence"]),
    )


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


def _fact(item: dict[str, Any]) -> CognitiveFact:
    source_id = str(item["source_id"])
    return CognitiveFact(
        fact_id=str(item["fact_id"]),
        key=str(item["key"]),
        value=str(item["value"]),
        source_id=source_id,
        observed_at=str(item.get("observed_at", "2026-07-22T00:00:00+00:00")),
        expires_at=str(item.get("expires_at", "2026-07-23T00:00:00+00:00")),
        confidence=float(item.get("confidence", 0.9)),
        version=int(item.get("version", 1)),
        status=CognitiveFactStatus(str(item.get("status", "active"))),
        kind=CognitiveFactKind(str(item.get("kind", "observation"))),
        source_kind=CognitiveFactSourceKind(str(item.get("source_kind", "world_evidence"))),
        supporting_source_ids=tuple(str(value) for value in item.get("supporting_source_ids", [source_id])),
    )


def _check(value: Any, expected: Any, label: str) -> dict[str, Any]:
    ok = value == expected
    return {"label": label, "passed": bool(ok), "expected": expected, "actual": value}


def _run_case(case: dict[str, Any], now: dt.datetime) -> tuple[bool, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    expect = case.get("expect", {})
    projection: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    fact_keys_projected: tuple[str, ...] = ()
    fact_uncertainties: tuple[str, ...] = ()
    resolution = None
    if case.get("entities"):
        entities = tuple(_entity(item) for item in case["entities"])
        relations = tuple(_relation(item) for item in case.get("relations", []))
        events = tuple(_event(item) for item in case.get("events", []))
        hypotheses = tuple(_hypothesis(item) for item in case.get("hypotheses", []))
        trials = tuple(_trial(item) for item in case.get("trials", []))
        resolution = resolve_counterfactual_trials(hypotheses, trials, events, now=now)
        model = build_head_world_model(
            entities=entities,
            relations=relations,
            events=events,
            causal_hypotheses=resolution.hypotheses,
            now=now,
        )
        projection = project_head_world_model(model, now=now)
        uncertainties = model.uncertainties
    if case.get("facts"):
        existing = tuple(_fact(item) for item in case["facts"])
        incoming = tuple(_fact(item) for item in case.get("incoming_facts", []))
        report = calibrate_facts_with_observations(existing, incoming)
        combined = list(report.written_facts)
        superseded_ids = {item.fact_id for item in report.superseded_facts}
        for item in existing:
            if item.fact_id in superseded_ids:
                combined.append(_fact({**_as_dict(item), "status": "superseded"}))
            else:
                combined.append(item)
        resolved = resolve_cognitive_facts(combined, now=now)
        fact_keys_projected = tuple(
            item.split("[", 1)[1].split("]", 1)[0] for item in project_cognitive_facts(resolved, now=now)
        )
        fact_uncertainties = project_cognitive_fact_uncertainties(resolved)
        if resolution is None and expect.get("refuted"):
            checks.append(_check(False, True, "refuted-requires-trials"))
    for marker in expect.get("projection_contains", []):
        checks.append(_check(any(marker in item for item in projection), True, f"projection_contains:{marker}"))
    for marker in expect.get("projection_excludes", []):
        checks.append(_check(any(marker in item for item in projection), False, f"projection_excludes:{marker}"))
    for marker in expect.get("uncertainties_contains", []):
        checks.append(_check(any(marker in item for item in uncertainties), True, f"uncertainties_contains:{marker}"))
    for marker in expect.get("uncertainties_excludes", []):
        checks.append(_check(any(marker in item for item in uncertainties), False, f"uncertainties_excludes:{marker}"))
    for key in expect.get("fact_keys_projected", []):
        checks.append(_check(key in fact_keys_projected, True, f"fact_keys_projected:{key}"))
    for key in expect.get("fact_keys_excluded", []):
        checks.append(_check(key in fact_keys_projected, False, f"fact_keys_excluded:{key}"))
    for marker in expect.get("fact_uncertainty_contains", []):
        checks.append(_check(any(marker in item for item in fact_uncertainties), True, f"fact_uncertainty_contains:{marker}"))
    if "admitted_unknown" in expect:
        checks.append(_check(not projection, expect["admitted_unknown"], "admitted_unknown"))
    if expect.get("refuted"):
        checks.append(_check(sorted(resolution.refuted_hypothesis_ids), sorted(expect["refuted"]), "refuted"))
    if expect.get("supported"):
        checks.append(_check(sorted(resolution.supported_hypothesis_ids), sorted(expect["supported"]), "supported"))
    if expect.get("confirmed"):
        confirmed = sorted(
            hypothesis.hypothesis_id for hypothesis in resolution.hypotheses if hypothesis.confirmed
        )
        checks.append(_check(confirmed, sorted(expect["confirmed"]), "confirmed"))
    return all(item["passed"] for item in checks), checks


def _as_dict(fact: CognitiveFact) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "key": fact.key,
        "value": fact.value,
        "source_id": fact.source_id,
        "observed_at": fact.observed_at,
        "expires_at": fact.expires_at,
        "confidence": fact.confidence,
        "version": fact.version,
        "status": fact.status.value,
        "kind": fact.kind.value,
        "source_kind": fact.source_kind.value,
        "supporting_source_ids": list(fact.supporting_source_ids),
    }


def evaluate_cases(document: dict[str, Any], *, now: dt.datetime | None = None) -> dict[str, Any]:
    current = now or dt.datetime.fromisoformat(str(document["now"]).replace("Z", "+00:00"))
    results = []
    passed = 0
    failed = 0
    for case in document["cases"]:
        ok, checks = _run_case(case, current)
        passed += int(ok)
        failed += int(not ok)
        results.append({"id": case["id"], "category": case["category"], "passed": ok, "checks": checks})
    return {
        "status": "PASS" if failed == 0 else "FAIL",
        "passed": passed,
        "failed": failed,
        "margin": round(passed / max(1, passed + failed), 4),
        "disclaimer": EVAL_DISCLAIMER,
        "cases": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the world model against the fixed case set.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    document = json.loads(args.cases.read_text(encoding="utf-8"))
    result = evaluate_cases(document)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "world-model-eval-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        lines = [
            "# 世界模型离线评估报告",
            "",
            f"- 状态: {result['status']}",
            f"- 通过: {result['passed']}/{result['passed'] + result['failed']}",
            f"- margin: {result['margin']}",
            f"- 声明: {EVAL_DISCLAIMER}",
        ]
        (args.output_dir / "world-model-eval-report.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
