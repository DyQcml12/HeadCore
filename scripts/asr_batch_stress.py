from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.audio.funasr_engine import FunAsrFileEngine, MODEL_PRESETS
from app.audio.quality_metrics import character_error_rate
from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets


DEFAULT_MANIFESTS = [
    PROJECT_ROOT / "data" / "asr_samples" / "manifest.json",
    PROJECT_ROOT / "data" / "asr_samples" / "stress_manifest.json",
]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "asr-batch-stress"


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"ASR manifest 不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"ASR manifest 必须是 list: {path}")
    return data


def load_samples(manifest_paths: list[Path]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        samples.extend(load_manifest(manifest_path))
    available = [sample for sample in samples if sample.get("path")]
    references = {
        str(sample.get("id")): sample
        for sample in available
        if sample.get("expected_text")
    }
    for sample in available:
        source = references.get(str(sample.get("source_sample_id") or ""))
        if source and not sample.get("expected_text"):
            sample["expected_text"] = source["expected_text"]
            sample["max_cer"] = stress_max_cer(sample)
    return available


def evaluate_result(
    sample: dict[str, Any], text: str, error: str | None
) -> tuple[bool, list[str], float | None]:
    reasons: list[str] = []
    if error:
        reasons.append("识别过程抛错")
    if not text.strip():
        reasons.append("识别文本为空")
    expected_contains = sample.get("expected_contains") or []
    missing = [term for term in expected_contains if term not in text]
    if missing and sample.get("hard_assert", True):
        reasons.append("缺少关键词: " + ",".join(missing))
    cer = None
    expected_text = str(sample.get("expected_text") or "").strip()
    if expected_text and text.strip():
        cer = character_error_rate(expected_text, text)
        max_cer = float(sample.get("max_cer", 0.2))
        if cer > max_cer:
            reasons.append(f"字符错误率超标: {cer:.4f} > {max_cer:.4f}")
    return not reasons, reasons, cer


def stress_max_cer(sample: dict[str, Any]) -> float:
    transform = str(sample.get("transform") or "")
    if transform == "truncate-tail":
        return 0.5
    if transform == "white-noise":
        return 0.35
    return 0.25


def run_batch(
    *,
    manifest_paths: list[Path],
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    model: str = "iic/SenseVoiceSmall",
    device: str = "cuda:0",
    engine: FunAsrFileEngine | None = None,
    limit: int | None = None,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "asr-batch-stress-report.md"
    result_path = output_dir / "asr-batch-stress-result.json"

    samples = load_samples(manifest_paths)
    if limit is not None:
        samples = samples[:limit]
    engine = engine or FunAsrFileEngine(model=model, device=device)
    results: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, start=1):
        audio_path = Path(str(sample["path"]))
        started = time.perf_counter()
        text = ""
        error = None
        if not audio_path.exists():
            error = f"音频文件不存在: {audio_path}"
            latency_ms = 0.0
        else:
            try:
                transcription = engine.transcribe_file(audio_path)
                text = (
                    transcription.text
                    if hasattr(transcription, "text")
                    else str(transcription)
                )
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
            except Exception as exc:
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                error = redact_secrets(str(exc))
        passed, reasons, cer = evaluate_result(sample, text, error)
        results.append(
            {
                "index": index,
                "id": sample.get("id", audio_path.stem),
                "sample_type": sample.get("sample_type", "unknown"),
                "language": sample.get("language", ""),
                "transform": sample.get("transform", ""),
                "audio_path": str(audio_path),
                "passed": passed,
                "text": text,
                "latency_ms": latency_ms,
                "cer": round(cer, 4) if cer is not None else None,
                "max_cer": sample.get("max_cer"),
                "reasons": reasons,
                "error": error,
            }
        )

    failed = [item for item in results if not item["passed"]]
    data = {
        "status": "PASS" if not failed else "FAIL",
        "provider": "funasr",
        "model": engine.model,
        "device": device,
        "manifest_paths": [str(path) for path in manifest_paths],
        "sample_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "results": results,
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
        "# ASR 批量真实/压力测试报告",
        "",
        f"- 结果: {data['status']}",
        f"- 开始时间: {started_at.isoformat(timespec='seconds')}",
        f"- 结束时间: {finished_at.isoformat(timespec='seconds')}",
        f"- 供应商: {data['provider']}",
        f"- 模型: {data['model']}",
        f"- 设备: {data['device']}",
        f"- 样本数: {data['sample_count']}",
        f"- 通过: {data['passed_count']}",
        f"- 失败: {data['failed_count']}",
        f"- 原始 JSON: `{result_path}`",
        "",
        "说明: `stress-derived` 是从真实公开/官方音频派生的极端测试样本，不是原始真实录音。",
        "",
    ]
    for result in data["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        reason_text = "无" if not result["reasons"] else "；".join(result["reasons"])
        lines.extend(
            [
                f"## {result['index']}. {result['id']} - {status}",
                "",
                f"- 类型: {result['sample_type']}",
                f"- 语言: {result['language'] or '未知'}",
                f"- 变换: {result['transform'] or '无'}",
                f"- 音频: `{result['audio_path']}`",
                f"- 耗时 ms: {result['latency_ms']}",
                f"- 文本: {result['text'] or '无'}",
                f"- CER: {result['cer'] if result['cer'] is not None else '无参考文本'}",
                f"- CER 阈值: {result['max_cer'] if result['max_cer'] is not None else '未设置'}",
                f"- 失败原因: {reason_text}",
                f"- 错误: {result['error'] or '无'}",
                "",
            ]
        )
    report_path.write_text(redact_secrets("\n".join(lines) + "\n"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行真实 FunASR 批量/极端压力测试。")
    parser.add_argument("--manifest", action="append", default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--model", default="iic/SenseVoiceSmall")
    parser.add_argument("--preset", choices=sorted(MODEL_PRESETS), default=None)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_paths = [Path(path) for path in args.manifest] if args.manifest else DEFAULT_MANIFESTS
    engine = FunAsrFileEngine.from_preset(args.preset, device=args.device) if args.preset else None
    report_path = run_batch(
        manifest_paths=manifest_paths,
        output_root=Path(args.output_root),
        model=args.model,
        device=args.device,
        engine=engine,
        limit=args.limit,
    )
    result_path = report_path.parent / "asr-batch-stress-result.json"
    status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"ASR 批量真实/压力测试报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
