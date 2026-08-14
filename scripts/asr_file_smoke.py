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

from app.audio.funasr_engine import FunAsrFileEngine
from app.audio.quality_metrics import character_error_rate
from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets


DEFAULT_MANIFEST = PROJECT_ROOT / "data" / "asr_samples" / "manifest.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "asr-file-smoke"


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"ASR sample manifest not found: {path}. Run scripts/download_asr_samples.py first."
        )
    samples = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(samples, list):
        raise ValueError("ASR sample manifest must be a list")
    return samples


def sample_passed(
    sample: dict[str, Any], text: str
) -> tuple[bool, list[str], float | None]:
    reasons: list[str] = []
    if not text.strip():
        reasons.append("识别文本为空")
    expected_contains = sample.get("expected_contains") or []
    missing = [item for item in expected_contains if item not in text]
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


def run_smoke(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    model: str = "iic/SenseVoiceSmall",
    device: str = "cuda:0",
    engine=None,
    limit: int | None = None,
) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "asr-file-smoke-report.md"
    result_path = output_dir / "asr-file-smoke-result.json"

    samples = load_manifest(manifest_path)
    if limit is not None:
        samples = samples[:limit]
    engine = engine or FunAsrFileEngine(model=model, device=device)
    results = []
    for sample in samples:
        audio_path = Path(str(sample["path"]))
        started = time.perf_counter()
        try:
            transcription = engine.transcribe_file(audio_path)
            text = (
                transcription.text
                if hasattr(transcription, "text")
                else str(transcription)
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            passed, reasons, cer = sample_passed(sample, text)
            results.append(
                {
                    "id": sample["id"],
                    "audio_path": str(audio_path),
                    "sample_type": sample.get("sample_type", ""),
                    "passed": passed,
                    "text": text,
                    "latency_ms": latency_ms,
                    "cer": round(cer, 4) if cer is not None else None,
                    "max_cer": sample.get("max_cer"),
                    "reasons": reasons,
                    "error": None,
                }
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            results.append(
                {
                    "id": sample["id"],
                    "audio_path": str(audio_path),
                    "sample_type": sample.get("sample_type", ""),
                    "passed": False,
                    "text": "",
                    "latency_ms": latency_ms,
                    "cer": None,
                    "max_cer": sample.get("max_cer"),
                    "reasons": ["识别过程抛错"],
                    "error": redact_secrets(str(exc)),
                }
            )

    failed = [item for item in results if not item["passed"]]
    data = {
        "status": "PASS" if not failed else "FAIL",
        "provider": "funasr",
        "model": model,
        "device": device,
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
        "# ASR 文件转写真实模型测试报告",
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
    ]
    for result in data["results"]:
        reason_text = "无" if not result["reasons"] else "；".join(result["reasons"])
        lines.extend(
            [
                f"## {result['id']}",
                "",
                f"- 结果: {'PASS' if result['passed'] else 'FAIL'}",
                f"- 类型: {result['sample_type'] or '未知'}",
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
    parser = argparse.ArgumentParser(description="运行真实 FunASR 文件转写 smoke 测试")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--model", default="iic/SenseVoiceSmall")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_smoke(
        manifest_path=Path(args.manifest),
        output_root=Path(args.output_root),
        model=args.model,
        device=args.device,
        limit=args.limit,
    )
    result_path = report_path.parent / "asr-file-smoke-result.json"
    status = json.loads(result_path.read_text(encoding="utf-8")).get("status", "FAIL")
    print(f"ASR 文件转写真实模型测试报告: {report_path}")
    print(f"结果: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
