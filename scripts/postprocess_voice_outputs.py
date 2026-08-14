from __future__ import annotations

import argparse
import json
import wave
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from scipy import signal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = PROJECT_ROOT / "data" / "hutao_voice" / "tests" / "voice_chat_pipeline" / "2026-06-30_001405"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "hutao_voice" / "tests" / "voice_chat_pipeline_postprocessed"

PROFILES = {
    "voice_clean": {
        "highpass_hz": 110.0,
        "lowpass_hz": 9000.0,
        "notch_hz": [50.0, 100.0],
        "notch_q": 32.0,
        "noise_gate_db": -48.0,
        "target_rms": 3300.0,
        "soft_clip": 0.94,
    },
    "bass_cut": {
        "highpass_hz": 155.0,
        "lowpass_hz": 8600.0,
        "notch_hz": [50.0, 100.0, 150.0],
        "notch_q": 32.0,
        "noise_gate_db": -46.0,
        "target_rms": 3100.0,
        "soft_clip": 0.92,
    },
    "dehiss": {
        "highpass_hz": 120.0,
        "lowpass_hz": 6800.0,
        "notch_hz": [50.0, 100.0],
        "notch_q": 32.0,
        "noise_gate_db": -44.0,
        "target_rms": 2900.0,
        "soft_clip": 0.90,
    },
}


def read_wav(path: Path) -> tuple[np.ndarray, wave._wave_params]:
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        frames = wav.readframes(wav.getnframes())
    if params.sampwidth != 2 or params.nchannels != 1:
        raise ValueError(f"Only 16-bit mono wav is supported: {path}")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    return samples, params


def write_wav(path: Path, samples: np.ndarray, params: wave._wave_params) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    frames = (clipped * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as wav:
        wav.setparams(params)
        wav.writeframes(frames)


def butter_highpass(samples: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0 or not len(samples):
        return samples
    sos = signal.butter(4, cutoff_hz, btype="highpass", fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, samples)


def butter_lowpass(samples: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0 or not len(samples):
        return samples
    sos = signal.butter(4, cutoff_hz, btype="lowpass", fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, samples)


def notch_filters(samples: np.ndarray, sample_rate: int, freqs: Iterable[float], q: float) -> np.ndarray:
    data = samples
    for freq in freqs:
        if freq <= 0 or freq >= sample_rate / 2:
            continue
        b, a = signal.iirnotch(freq, q, fs=sample_rate)
        data = signal.filtfilt(b, a, data)
    return data


def noise_gate(samples: np.ndarray, threshold_db: float) -> np.ndarray:
    if not len(samples):
        return samples
    threshold = 10 ** (threshold_db / 20.0)
    window = max(128, min(1024, len(samples) // 20))
    kernel = np.ones(window, dtype=np.float64) / window
    envelope = np.sqrt(np.convolve(samples * samples, kernel, mode="same"))
    gate = np.clip((envelope - threshold * 0.55) / max(threshold * 0.45, 1e-9), 0.0, 1.0)
    return samples * gate


def normalize_rms(samples: np.ndarray, target_rms: float) -> np.ndarray:
    if not len(samples):
        return samples
    current = float(np.sqrt(np.mean(samples * samples)) * 32768.0)
    if current <= 1:
        return samples
    gain = min(1.4, max(0.4, target_rms / current))
    return samples * gain


def soft_limit(samples: np.ndarray, amount: float) -> np.ndarray:
    threshold = max(0.5, min(0.99, amount))
    signs = np.sign(samples)
    values = np.abs(samples)
    excess = values - threshold
    limited = threshold + (1.0 - threshold) * np.tanh(excess / (1.0 - threshold))
    return np.where(values <= threshold, samples, signs * limited)


def process(samples: np.ndarray, sample_rate: int, profile: dict[str, object]) -> np.ndarray:
    data = butter_highpass(samples, sample_rate, float(profile["highpass_hz"]))
    data = notch_filters(data, sample_rate, profile.get("notch_hz", []), float(profile.get("notch_q", 32.0)))
    data = butter_lowpass(data, sample_rate, float(profile["lowpass_hz"]))
    data = noise_gate(data, float(profile["noise_gate_db"]))
    data = normalize_rms(data, float(profile["target_rms"]))
    data = soft_limit(data, float(profile["soft_clip"]))
    return data


def band_energy_ratio(samples: np.ndarray, sample_rate: int, low_hz: float, high_hz: float) -> float:
    if len(samples) < 2:
        return 0.0
    spectrum = np.fft.rfft(samples * np.hanning(len(samples)))
    power = np.abs(spectrum) ** 2
    freqs = np.fft.rfftfreq(len(samples), 1 / sample_rate)
    total = float(np.sum(power))
    if total <= 0:
        return 0.0
    mask = (freqs >= low_hz) & (freqs < high_hz)
    return round(float(np.sum(power[mask]) / total), 6)


def wav_stats(samples: np.ndarray, sample_rate: int) -> dict[str, object]:
    if not len(samples):
        return {"duration_seconds": 0, "rms": 0, "peak": 0, "clip_ratio": 0}
    rms = float(np.sqrt(np.mean(samples * samples)) * 32768.0)
    peak = float(np.max(np.abs(samples)) * 32768.0)
    clipped = int(np.sum(np.abs(samples) >= 0.999))
    return {
        "duration_seconds": round(len(samples) / sample_rate, 3),
        "rms": round(rms, 1),
        "peak": round(peak, 1),
        "clip_ratio": round(clipped / len(samples), 6),
        "low_bass_ratio_0_120hz": band_energy_ratio(samples, sample_rate, 0.0, 120.0),
        "bass_ratio_120_250hz": band_energy_ratio(samples, sample_rate, 120.0, 250.0),
        "speech_ratio_250_5000hz": band_energy_ratio(samples, sample_rate, 250.0, 5000.0),
        "hiss_ratio_7000hz_plus": band_energy_ratio(samples, sample_rate, 7000.0, sample_rate / 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Postprocess generated Hu Tao voice WAV files.")
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-name", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_root = Path(args.input_root)
    run_name = args.run_name or f"{input_root.name}_noise_bass_v2"
    output_root = Path(args.output_root) / run_name
    input_files = sorted(input_root.rglob("*_combined.wav"))
    if not input_files:
        raise FileNotFoundError(f"No *_combined.wav files under {input_root}")

    results: list[dict[str, object]] = []
    for input_path in input_files:
        samples, params = read_wav(input_path)
        relative = input_path.relative_to(input_root)
        sample_rate = params.framerate
        item = {
            "input_path": str(input_path),
            "input_stats": wav_stats(samples, sample_rate),
            "outputs": [],
        }
        for name, profile in PROFILES.items():
            processed = process(samples, sample_rate, profile)
            output_path = output_root / name / relative
            write_wav(output_path, processed, params)
            item["outputs"].append(
                {
                    "profile": name,
                    "profile_settings": profile,
                    "output_path": str(output_path),
                    "output_stats": wav_stats(processed, sample_rate),
                }
            )
        results.append(item)

    report = {
        "status": "PASS",
        "input_root": str(input_root),
        "output_root": str(output_root),
        "profiles": PROFILES,
        "results": results,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    result_path = output_root / "postprocess_voice_outputs.json"
    report_path = output_root / "postprocess_voice_outputs.md"
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(build_report(report, result_path), encoding="utf-8")
    print(f"后处理报告: {report_path}")
    print("结果: PASS")
    return 0


def build_report(report: dict[str, object], result_path: Path) -> str:
    lines = [
        "# 胡桃语音后处理测试",
        "",
        f"- 结果: {report['status']}",
        f"- 输入目录: `{report['input_root']}`",
        f"- 输出目录: `{report['output_root']}`",
        f"- 原始 JSON: `{result_path}`",
        "",
    ]
    for item in report["results"]:
        lines.extend(
            [
                f"## {Path(item['input_path']).name}",
                "",
                f"- 原始音频: `{item['input_path']}`",
                f"- 原始统计: {item['input_stats']}",
            ]
        )
        for output in item["outputs"]:
            lines.extend(
                [
                    f"- {output['profile']}: `{output['output_path']}`",
                    f"  - 参数: {output['profile_settings']}",
                    f"  - 统计: {output['output_stats']}",
                ]
            )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
