from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.audio.funasr_engine import FunAsrFileEngine
from app.audio.quality import evaluate_asr_text_quality
from app.core.security import redact_secrets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one isolated ASR preset probe.")
    parser.add_argument("--preset", required=True)
    parser.add_argument("--audio-path", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    text = ""
    error = None
    try:
        engine = FunAsrFileEngine.from_preset(args.preset, device=args.device)
        text = engine.transcribe_file(Path(args.audio_path))
    except Exception as exc:
        error = redact_secrets(str(exc))
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    quality = evaluate_asr_text_quality(text)
    data = {
        "preset": args.preset,
        "audio_path": args.audio_path,
        "text": text,
        "latency_ms": latency_ms,
        "quality_passed": quality.passed and error is None,
        "quality_score": 0.0 if error else quality.score,
        "quality_reasons": [*quality.reasons, *(["engine_error"] if error else [])],
        "error": error,
    }
    Path(args.output).write_text(
        redact_secrets(json.dumps(data, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )
    return 0 if data["quality_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
