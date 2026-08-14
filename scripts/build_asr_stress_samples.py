from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_MANIFEST = PROJECT_ROOT / "data" / "asr_samples" / "manifest.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "asr_samples" / "stress"
DEFAULT_OUTPUT_MANIFEST = PROJECT_ROOT / "data" / "asr_samples" / "stress_manifest.json"

STRESS_VARIANTS = [
    "low-volume",
    "white-noise",
    "front-back-silence",
    "truncate-tail",
    "speed-up",
]


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"ASR manifest 不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("ASR manifest 必须是 list")
    return data


def ensure_mono_float32(audio_path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(str(audio_path), always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32, copy=False)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 1.0:
        audio = audio / peak
    return audio, int(sample_rate)


def safe_write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.nan_to_num(audio).astype(np.float32, copy=False)
    audio = np.clip(audio, -0.98, 0.98)
    sf.write(str(path), audio, sample_rate, subtype="PCM_16")


def transform_audio(audio: np.ndarray, sample_rate: int, variant: str) -> np.ndarray:
    if variant == "low-volume":
        return audio * 0.18
    if variant == "white-noise":
        rng = np.random.default_rng(20260628)
        noise = rng.normal(0.0, 0.035, size=audio.shape).astype(np.float32)
        return audio * 0.82 + noise
    if variant == "front-back-silence":
        silence = np.zeros(int(sample_rate * 0.9), dtype=np.float32)
        return np.concatenate([silence, audio, silence])
    if variant == "truncate-tail":
        keep = max(int(audio.shape[0] * 0.68), min(audio.shape[0], int(sample_rate * 0.7)))
        return audio[:keep]
    if variant == "speed-up":
        target_len = max(1, int(audio.shape[0] / 1.12))
        return signal.resample(audio, target_len).astype(np.float32)
    raise ValueError(f"未知压力变体: {variant}")


def build_stress_samples(
    *,
    source_manifest: Path = DEFAULT_SOURCE_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    output_manifest: Path = DEFAULT_OUTPUT_MANIFEST,
    max_sources: int = 4,
) -> Path:
    source_samples = [
        item
        for item in load_manifest(source_manifest)
        if item.get("language") in {"zh", "yue"} and Path(str(item.get("path", ""))).exists()
    ][:max_sources]
    if not source_samples:
        raise RuntimeError("没有可用于压力样本派生的真实中文/粤语音频。")

    output_dir.mkdir(parents=True, exist_ok=True)
    stress_manifest: list[dict[str, Any]] = []
    for sample in source_samples:
        source_path = Path(str(sample["path"]))
        try:
            audio, sample_rate = ensure_mono_float32(source_path)
        except Exception as exc:
            stress_manifest.append(
                {
                    "id": f"{sample['id']}-stress-load-failed",
                    "sample_type": "stress-derived",
                    "source_sample_id": sample["id"],
                    "source_path": str(source_path),
                    "language": sample.get("language", "zh"),
                    "expected_contains": [],
                    "hard_assert": False,
                    "path": "",
                    "transform": "load-failed",
                    "error": str(exc),
                }
            )
            continue
        for variant in STRESS_VARIANTS:
            output_path = output_dir / f"{sample['id']}__{variant}.wav"
            transformed = transform_audio(audio, sample_rate, variant)
            safe_write_wav(output_path, transformed, sample_rate)
            stress_manifest.append(
                {
                    "id": f"{sample['id']}__{variant}",
                    "sample_type": "stress-derived",
                    "source_sample_id": sample["id"],
                    "source_path": str(source_path),
                    "language": sample.get("language", "zh"),
                    "expected_contains": sample.get("expected_contains", []),
                    "expected_text": sample.get("expected_text", ""),
                    "max_cer": stress_max_cer(sample, variant),
                    "hard_assert": False,
                    "path": str(output_path),
                    "transform": variant,
                    "source": "Derived from real ASR sample for robustness testing.",
                    "license_note": sample.get("license_note", ""),
                }
            )

    output_manifest.write_text(
        json.dumps(stress_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_manifest


def stress_max_cer(sample: dict[str, Any], variant: str) -> float:
    if not sample.get("expected_text"):
        return 1.0
    if variant == "truncate-tail":
        return 0.5
    if variant == "white-noise":
        return 0.35
    return 0.25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于真实音频生成 ASR 极端压力测试样本。")
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-manifest", default=str(DEFAULT_OUTPUT_MANIFEST))
    parser.add_argument("--max-sources", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = build_stress_samples(
        source_manifest=Path(args.source_manifest),
        output_dir=Path(args.output_dir),
        output_manifest=Path(args.output_manifest),
        max_sources=max(args.max_sources, 1),
    )
    print(f"ASR 压力样本 manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
