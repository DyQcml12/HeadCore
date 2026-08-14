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

from app.audio.funasr_engine import MODEL_PRESETS, FunAsrFileEngine
from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets
from scripts.asr_batch_stress import DEFAULT_MANIFESTS, run_batch


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "asr-model-compare"


def load_result(result_path: Path) -> dict[str, Any]:
    return json.loads(result_path.read_text(encoding="utf-8"))


def summarize_result(data: dict[str, Any]) -> dict[str, Any]:
    latencies = [float(item["latency_ms"]) for item in data.get("results", [])]
    return {
        "status": data.get("status", "FAIL"),
        "model": data.get("model", ""),
        "sample_count": data.get("sample_count", 0),
        "passed_count": data.get("passed_count", 0),
        "failed_count": data.get("failed_count", 0),
        "total_latency_ms": round(sum(latencies), 2),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
    }


def run_compare(
    *,
    presets: list[str],
    manifest_paths: list[Path],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    device: str = "cuda:0",
    limit: int | None = None,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "asr-model-compare-report.md"
    result_path = output_dir / "asr-model-compare-result.json"

    model_runs: list[dict[str, Any]] = []
    for preset in presets:
        if preset not in MODEL_PRESETS:
            raise ValueError(f"未知 ASR 预设: {preset}")
        model = str(MODEL_PRESETS[preset]["model"])
        run_output_root = output_dir / preset
        engine = FunAsrFileEngine.from_preset(preset, device=device)
        run_report = run_batch(
            manifest_paths=manifest_paths,
            output_root=run_output_root,
            model=model,
            device=device,
            engine=engine,
            limit=limit,
        )
        run_result = load_result(run_report.parent / "asr-batch-stress-result.json")
        model_runs.append(
            {
                "preset": preset,
                "report_path": str(run_report),
                "result_path": str(run_report.parent / "asr-batch-stress-result.json"),
                "summary": summarize_result(run_result),
                "results": run_result.get("results", []),
            }
        )

    failed_runs = [run for run in model_runs if run["summary"]["status"] != "PASS"]
    data = {
        "status": "PASS" if not failed_runs else "FAIL",
        "device": device,
        "manifest_paths": [str(path) for path in manifest_paths],
        "presets": presets,
        "model_runs": model_runs,
    }
    result_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    write_report(report_path=report_path, result_path=result_path, data=data, started_at=started_at)
    return report_path


def write_report(
    *,
    report_path: Path,
    result_path: Path,
    data: dict[str, Any],
    started_at: dt.datetime,
) -> None:
    finished_at = dt.datetime.now()
    lines = [
        "# ASR 模型横评报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- 设备: {data['device']}",
        f"- 原始 JSON: `{result_path}`",
        "",
        "## 汇总",
        "",
        "| 预设 | 模型 | 结果 | 样本 | 通过 | 失败 | 平均耗时 ms | 总耗时 ms |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in data["model_runs"]:
        summary = run["summary"]
        lines.append(
            "| {preset} | {model} | {status} | {sample_count} | {passed_count} | {failed_count} | {avg_latency_ms} | {total_latency_ms} |".format(
                preset=run["preset"],
                **summary,
            )
        )
    lines.extend(["", "## 单条结果", ""])
    for run in data["model_runs"]:
        lines.extend([f"### {run['preset']} / {run['summary']['model']}", ""])
        for item in run["results"]:
            status = "PASS" if item["passed"] else "FAIL"
            lines.extend(
                [
                    f"- `{item['id']}`: {status}, {item['latency_ms']} ms, `{item['text'] or '无'}`",
                ]
            )
        lines.append("")
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用同一批真实音频横评多个 FunASR 模型预设。")
    parser.add_argument(
        "--preset",
        action="append",
        default=None,
        help="可重复传入。默认比较 sensevoice-small 与 fun-asr-nano。",
    )
    parser.add_argument("--manifest", action="append", default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    presets = args.preset or ["sensevoice-small", "fun-asr-nano"]
    manifest_paths = [Path(path) for path in args.manifest] if args.manifest else DEFAULT_MANIFESTS
    report_path = run_compare(
        presets=presets,
        manifest_paths=manifest_paths,
        output_root=Path(args.output_root),
        device=args.device,
        limit=args.limit,
    )
    result_path = report_path.parent / "asr-model-compare-result.json"
    status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"ASR 模型横评报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
