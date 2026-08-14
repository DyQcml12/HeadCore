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

from app.head.blind_review import evaluate_blind_reviews, load_review_rows
from app.core.security import redact_secrets


def import_reviews(manifest_path: Path, submission_paths: list[Path], output_root: Path) -> Path:
    package = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = evaluate_blind_reviews(package, [(path, load_review_rows(path)) for path in submission_paths])
    output_dir = output_root / dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "headcore-blind-review-result.json"
    report_path = output_dir / "headcore-blind-review-report.md"
    result_path.write_text(redact_secrets(json.dumps(result, ensure_ascii=False, indent=2)), encoding="utf-8")
    report_path.write_text(redact_secrets(_report(result, result_path)), encoding="utf-8")
    return report_path


def _report(result: dict[str, Any], result_path: Path) -> str:
    lines = [
        "# HeadCore External Blind Review",
        "",
        f"- Reviewers: {result['reviewer_count']}",
        f"- Items / judgments: {result['item_count']} / {result['judgment_count']}",
        f"- Raw agreement: {result['raw_agreement']:.2%}",
        f"- Unanimous rate: {result['unanimous_rate']:.2%}",
        f"- Fleiss' Kappa: {result['fleiss_kappa']:.4f}",
        f"- HeadCore / majority alignment: {_percent(result['headcore_consensus_alignment'])}",
        f"- HeadCore pairwise vote win rate: {result['headcore_vote_win_rate']:.2%}",
        f"- Tied items: {result['tie_count']}",
        f"- Average confidence: {result['average_confidence'] if result['average_confidence'] is not None else 'not provided'}",
        f"- Raw JSON: `{result_path}`",
        "",
        "This report measures external preference and agreement. It does not prove human-equivalent thinking or a complete world model.",
    ]
    return "\n".join(lines)


def _percent(value: float | None) -> str:
    return "n/a (all items tied)" if value is None else f"{value:.2%}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and aggregate completed HeadCore blind reviews.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("submissions", nargs="+", type=Path)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "logs" / "head-planning-human-review")
    args = parser.parse_args()
    print(import_reviews(args.manifest, args.submissions, args.output_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
