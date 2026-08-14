from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.audio.funasr_engine import FunAsrFileEngine
from app.perception.contracts import PerceptionInput
from app.perception.pipeline import PerceptionPipeline
from app.perception.adapters import AsrObservationAdapter
from app.perception.validation import InputPolicy


def run_audio_smoke(path: Path, *, preset: str, device: str) -> dict[str, object]:
    if not path.is_file():
        return {"status": "SKIP", "reason": "audio_file_missing", "path": str(path)}
    engine = FunAsrFileEngine.from_preset(preset, device=device)
    adapter = AsrObservationAdapter(engine)
    value = PerceptionInput(
        modality="audio",
        source="perception_smoke",
        local_path=path,
        declared_mime=_audio_mime(path),
    )
    result = PerceptionPipeline(input_policy=InputPolicy(allowed_roots=(path.parent,))).run(
        value,
        (lambda item, fallback: adapter.observe(item.local_path, fallback=fallback),),
    )
    trace = result.traces[-1] if result.traces else None
    return {
        "status": "PASS" if result.quality != "failed" else "FAIL",
        "quality": result.quality,
        "confidence": result.confidence,
        "text_length": len(result.text),
        "memory_decision": result.memory_eligibility.decision,
        "provider": trace.provider if trace else "",
        "model": trace.model if trace else "",
        "error_code": trace.error_code if trace else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional real S3 perception smoke test")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--preset", default="sensevoice-small")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    result = run_audio_smoke(args.audio, preset=args.preset, device=args.device)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASS", "SKIP"} else 1


def _audio_mime(path: Path) -> str:
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }.get(path.suffix.lower(), "application/octet-stream")


if __name__ == "__main__":
    raise SystemExit(main())
