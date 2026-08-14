from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.head.blind_review import build_blind_review_package, write_manifest, write_review_csv
from app.head.calibration import load_pairwise_preferences
from app.head.evaluation import evaluate_planning_scenarios, load_planning_scenarios

DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "testing" / "headcore-blind-review"


def export_package(output_dir: Path, *, seed: str) -> dict[str, Path]:
    scenarios = load_planning_scenarios(PROJECT_ROOT / "data" / "head_planning_scenarios.json")
    preferences = load_pairwise_preferences(PROJECT_ROOT / "data" / "head_planning_pairwise_preferences.json")
    scenario_results = evaluate_planning_scenarios(scenarios)["results"]
    inputs = {str(item["id"]): str(item["user_input"]) for item in scenarios}
    for result in scenario_results:
        result["user_input"] = inputs[result["id"]]
    package = build_blind_review_package(scenario_results, preferences, seed=seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    public_path = output_dir / "headcore-planning-blind-review.csv"
    manifest_path = output_dir / "headcore-planning-blind-manifest.json"
    workbook_input = output_dir / "headcore-planning-blind-workbook-input.json"
    write_review_csv(package, public_path)
    write_manifest(package, manifest_path)
    workbook_input.write_text(json.dumps(package["public_items"], ensure_ascii=False, indent=2), encoding="utf-8")
    return {"csv": public_path, "manifest": manifest_path, "workbook_input": workbook_input}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a blind external review package for HeadCore planning.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", default="hutao-headcore-blind-review-v1")
    parser.add_argument("--build-xlsx", action="store_true")
    args = parser.parse_args()
    paths = export_package(args.output_dir, seed=args.seed)
    if args.build_xlsx:
        subprocess.run(["node", str(PROJECT_ROOT / "scripts" / "build_head_planning_blind_review.mjs"), str(paths["workbook_input"]), str(args.output_dir)], check=True)
    print(paths["csv"])
    print(paths["manifest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
