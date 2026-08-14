from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.audio.funasr_engine import MODEL_PRESETS
from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets
from scripts.asr_batch_stress import load_samples


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "asr-isolated-model-compare"
DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "asr_samples" / "manifest.json"
WORKER = PROJECT_ROOT / "scripts" / "asr_isolated_probe_worker.py"


def run_compare(
    *,
    presets: list[str],
    manifest_paths: list[Path],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    device: str = "cuda:0",
    limit: int = 2,
    timeout_seconds: float = 180.0,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "asr-isolated-model-compare-report.md"
    result_path = output_dir / "asr-isolated-model-compare-result.json"

    samples = load_samples(manifest_paths)[:limit]
    results: list[dict[str, Any]] = []
    for sample in samples:
        audio_path = Path(str(sample["path"]))
        sample_runs = []
        for preset in presets:
            if preset not in MODEL_PRESETS:
                raise ValueError(f"Unknown ASR preset: {preset}")
            run_output = output_dir / f"{sample.get('id', audio_path.stem)}__{preset}.json"
            run_data = run_probe(
                preset=preset,
                audio_path=audio_path,
                output_path=run_output,
                device=device,
                timeout_seconds=timeout_seconds,
            )
            sample_runs.append(run_data)
        selected = select_best_run(sample_runs)
        results.append(
            {
                "id": sample.get("id", audio_path.stem),
                "audio_path": str(audio_path),
                "sample_type": sample.get("sample_type", ""),
                "selected_preset": selected.get("preset", ""),
                "selection_reason": build_selection_reason(selected, sample_runs),
                "runs": sample_runs,
            }
        )

    failed = [
        run
        for result in results
        for run in result["runs"]
        if not run.get("quality_passed")
    ]
    data = {
        "status": "PASS" if not failed else "WARN",
        "device": device,
        "timeout_seconds": timeout_seconds,
        "manifest_paths": [str(path) for path in manifest_paths],
        "presets": presets,
        "sample_count": len(results),
        "failed_run_count": len(failed),
        "results": results,
    }
    result_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
    return report_path


def run_probe(
    *,
    preset: str,
    audio_path: Path,
    output_path: Path,
    device: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(WORKER),
        "--preset",
        preset,
        "--audio-path",
        str(audio_path),
        "--device",
        device,
        "--output",
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if output_path.exists():
            data = json.loads(output_path.read_text(encoding="utf-8"))
        else:
            data = {
                "preset": preset,
                "audio_path": str(audio_path),
                "text": "",
                "latency_ms": 0.0,
                "quality_passed": False,
                "quality_score": 0.0,
                "quality_reasons": ["missing_worker_output"],
                "error": "Worker did not write output.",
            }
        data["return_code"] = completed.returncode
        data["timed_out"] = False
    except subprocess.TimeoutExpired:
        data = {
            "preset": preset,
            "audio_path": str(audio_path),
            "text": "",
            "latency_ms": timeout_seconds * 1000,
            "quality_passed": False,
            "quality_score": 0.0,
            "quality_reasons": ["timeout"],
            "error": f"ASR probe timed out after {timeout_seconds} seconds.",
            "return_code": None,
            "timed_out": True,
        }
    return data


def select_best_run(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        runs,
        key=lambda item: (
            bool(item.get("quality_passed")),
            float(item.get("quality_score", 0.0)),
            bool(str(item.get("text", "")).strip()),
            -float(item.get("latency_ms", 0.0)),
        ),
        reverse=True,
    )[0]


def build_selection_reason(selected: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    if len(runs) == 1:
        return "single_candidate"
    if selected.get("quality_passed"):
        return "best_quality_passed"
    return "best_available_low_quality"


def write_report(
    *,
    report_path: Path,
    result_path: Path,
    data: dict[str, Any],
    started_at: dt.datetime,
) -> None:
    finished_at = dt.datetime.now()
    lines = [
        "# ASR Isolated Model Compare Report",
        "",
        f"- Result: {data['status']}",
        f"- Started: {started_at.isoformat(timespec='seconds')}",
        f"- Finished: {finished_at.isoformat(timespec='seconds')}",
        f"- Device: {data['device']}",
        f"- Timeout seconds: {data['timeout_seconds']}",
        f"- Presets: {', '.join(data['presets'])}",
        f"- Sample count: {data['sample_count']}",
        f"- Failed run count: {data['failed_run_count']}",
        f"- Raw JSON: `{result_path}`",
        "",
    ]
    for result in data["results"]:
        lines.extend(
            [
                f"## {result['id']}",
                "",
                f"- Selected preset: {result['selected_preset']}",
                f"- Selection reason: {result['selection_reason']}",
                f"- Audio: `{result['audio_path']}`",
                "",
                "| Preset | Passed | Score | Latency ms | Timed out | Reasons | Text |",
                "| --- | --- | ---: | ---: | --- | --- | --- |",
            ]
        )
        for run in result["runs"]:
            reasons = ";".join(run.get("quality_reasons") or [])
            text = str(run.get("text", "")).replace("|", "\\|")
            lines.append(
                f"| {run['preset']} | {run['quality_passed']} | {run['quality_score']} | "
                f"{run['latency_ms']} | {run.get('timed_out')} | {reasons or 'none'} | {text or 'none'} |"
            )
        lines.append("")
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated ASR model compare with per-run timeout.")
    parser.add_argument("--preset", action="append", default=None)
    parser.add_argument("--manifest", action="append", default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_compare(
        presets=args.preset or ["sensevoice-small", "fun-asr-nano"],
        manifest_paths=[Path(path) for path in args.manifest] if args.manifest else [DEFAULT_MANIFEST],
        output_root=Path(args.output_root),
        device=args.device,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
    )
    data = json.loads((report_path.parent / "asr-isolated-model-compare-result.json").read_text(encoding="utf-8"))
    print(f"ASR isolated model compare report: {report_path}")
    print(f"Result: {data.get('status')}")
    return 0 if data.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
