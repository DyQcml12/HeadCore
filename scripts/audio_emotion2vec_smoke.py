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

from app.audio.emotion_engine import Emotion2VecEngine
from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "logs" / "audio-emotion2vec-smoke"
DEFAULT_MODEL = "iic/emotion2vec_plus_large"

ZH_LABELS = {
    "neutral": "\u4e2d\u6027",
    "happy": "\u5f00\u5fc3",
    "sad": "\u4f24\u5fc3",
    "angry": "\u751f\u6c14",
    "fearful": "\u5bb3\u6015",
    "unknown": "\u672a\u6807\u6ce8",
}
ZH_NONE = "\u65e0"


def default_samples() -> list[dict[str, Any]]:
    sample_root = PROJECT_ROOT / "data" / "asr_emotion_web_samples" / "2026-06-29_161455"
    return [
        {
            "name": "\u4e2d\u6027\u6837\u672c",
            "expected": "neutral",
            "path": sample_root / "ravdess-neutral-actor01-cdn.wav",
        },
        {
            "name": "\u5f00\u5fc3\u6837\u672c",
            "expected": "happy",
            "path": sample_root / "ravdess-happy-actor01-cdn.wav",
        },
        {
            "name": "\u4f24\u5fc3\u6837\u672c",
            "expected": "sad",
            "path": sample_root / "ravdess-sad-actor01-cdn.wav",
        },
        {
            "name": "\u751f\u6c14\u6837\u672c",
            "expected": "angry",
            "path": sample_root / "ravdess-angry-actor01-cdn.wav",
        },
        {
            "name": "\u5bb3\u6015\u6837\u672c",
            "expected": "fearful",
            "path": sample_root / "ravdess-fearful-actor01-cdn.wav",
        },
        {
            "name": "\u4e2d\u6587\u516c\u5f00\u6837\u672c",
            "expected": "unknown",
            "path": PROJECT_ROOT / "data" / "asr_samples" / "funasr-zh-example-001.wav",
        },
    ]


def run_smoke(*, model: str, output_root: Path) -> Path:
    started_at = dt.datetime.now()
    timestamp = started_at.strftime("%Y-%m-%d_%H%M%S")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "audio-emotion2vec-smoke-result.json"
    report_path = output_dir / "audio-emotion2vec-smoke-report.md"

    engine = Emotion2VecEngine(model=model)
    results: list[dict[str, Any]] = []
    for sample in default_samples():
        expected = str(sample["expected"])
        audio_path = Path(sample["path"])
        item: dict[str, Any] = {
            "name": sample["name"],
            "expected": expected,
            "expected_zh": ZH_LABELS.get(expected, expected),
            "audio_path": str(audio_path),
        }
        try:
            result = engine.analyze_file(audio_path)
            matched = expected == "unknown" or result.emotion == expected
            item.update(
                {
                    "detected": result.emotion,
                    "detected_zh": ZH_LABELS.get(result.emotion or "", result.emotion),
                    "confidence": result.emotion_confidence,
                    "raw_label": result.raw_label,
                    "matched": matched,
                    "error": result.error,
                }
            )
        except Exception as exc:
            item.update(
                {
                    "detected": None,
                    "detected_zh": None,
                    "confidence": None,
                    "raw_label": None,
                    "matched": False,
                    "error": redact_secrets(str(exc)),
                }
            )
        results.append(item)

    known_results = [item for item in results if item["expected"] != "unknown"]
    matched_count = sum(1 for item in known_results if item["matched"])
    status = "PASS" if matched_count >= 4 else "FAIL"
    data = {
        "status": status,
        "model": model,
        "known_sample_count": len(known_results),
        "matched_count": matched_count,
        "started_at": started_at.isoformat(timespec="seconds"),
        "results": results,
    }
    result_path.write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    report_path.write_text(
        redact_secrets(build_report(data, result_path)),
        encoding="utf-8",
    )
    return report_path


def build_report(data: dict[str, Any], result_path: Path) -> str:
    lines = [
        "# \u8bed\u97f3\u60c5\u7eea\u8bc6\u522b\u6a21\u578b\u771f\u5b9e\u6d4b\u8bd5\u62a5\u544a",
        "",
        f"- \u7ed3\u679c: {data['status']}",
        f"- \u6a21\u578b: {data['model']}",
        f"- \u5df2\u77e5\u60c5\u7eea\u6837\u672c\u6570: {data['known_sample_count']}",
        f"- \u547d\u4e2d\u6570: {data['matched_count']}",
        f"- \u539f\u59cb JSON: `{result_path}`",
        "",
    ]
    for item in data["results"]:
        lines.extend(
            [
                f"## {item['name']}",
                "",
                f"- \u9884\u671f\u60c5\u7eea: {item['expected_zh']} ({item['expected']})",
                f"- \u8bc6\u522b\u60c5\u7eea: {item['detected_zh']} ({item['detected']})",
                f"- \u7f6e\u4fe1\u5ea6: {item['confidence']}",
                f"- \u539f\u59cb\u6807\u7b7e: {item['raw_label']}",
                f"- \u662f\u5426\u547d\u4e2d: {item['matched']}",
                f"- \u9519\u8bef: {item['error'] or ZH_NONE}",
                f"- \u97f3\u9891: `{item['audio_path']}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real emotion2vec audio emotion smoke test.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run_smoke(model=args.model, output_root=Path(args.output_root))
    result = json.loads((report_path.parent / "audio-emotion2vec-smoke-result.json").read_text(encoding="utf-8"))
    print(f"语音情绪识别真实测试报告: {report_path}")
    print(f"结果: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
