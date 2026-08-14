from __future__ import annotations

import struct
import wave
from pathlib import Path


def append_wav_files(
    input_paths: list[Path],
    output_path: Path,
    pause_ms: list[int] | None = None,
    fade_ms: int = 8,
) -> None:
    if not input_paths:
        raise ValueError("input_paths is empty")
    pause_ms = pause_ms or [0 for _ in input_paths]
    with wave.open(str(input_paths[0]), "rb") as first:
        params = first.getparams()
        sample_rate = first.getframerate()
        sample_width = first.getsampwidth()
        channels = first.getnchannels()
    frames: list[bytes] = []
    for index, path in enumerate(input_paths):
        with wave.open(str(path), "rb") as wav:
            if wav.getframerate() != sample_rate or wav.getsampwidth() != sample_width or wav.getnchannels() != channels:
                raise ValueError(f"WAV format mismatch: {path}")
            frames.append(apply_short_fade(wav.readframes(wav.getnframes()), sample_rate, sample_width, channels, fade_ms))
        pause_frames = int(sample_rate * (pause_ms[index] if index < len(pause_ms) else 0) / 1000)
        if pause_frames:
            frames.append(b"\x00" * pause_frames * sample_width * channels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output:
        output.setparams(params)
        output.writeframes(b"".join(frames))


def apply_short_fade(frames: bytes, sample_rate: int, sample_width: int, channels: int, fade_ms: int) -> bytes:
    if sample_width != 2 or channels != 1 or fade_ms <= 0:
        return frames
    samples = list(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    fade_len = min(len(samples) // 2, int(sample_rate * fade_ms / 1000))
    if fade_len <= 0:
        return frames
    for index in range(fade_len):
        ratio = index / fade_len
        samples[index] = int(samples[index] * ratio)
        samples[-index - 1] = int(samples[-index - 1] * ratio)
    return struct.pack("<" + "h" * len(samples), *samples)


def trim_wav_start(
    input_path: Path,
    output_path: Path | None = None,
    *,
    trim_ms: int = 120,
    fade_ms: int = 8,
) -> Path:
    output = output_path or input_path
    with wave.open(str(input_path), "rb") as wav:
        params = wav.getparams()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        channels = wav.getnchannels()
        frames = wav.readframes(wav.getnframes())
    trim_bytes = int(sample_rate * max(trim_ms, 0) / 1000) * sample_width * channels
    trim_bytes -= trim_bytes % max(sample_width * channels, 1)
    trimmed = frames[min(trim_bytes, len(frames)) :]
    faded = apply_fade_in(trimmed, sample_rate, sample_width, channels, fade_ms)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setparams(params)
        wav.writeframes(faded)
    return output


def apply_fade_in(frames: bytes, sample_rate: int, sample_width: int, channels: int, fade_ms: int) -> bytes:
    if sample_width != 2 or channels != 1 or fade_ms <= 0:
        return frames
    samples = list(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    fade_len = min(len(samples), int(sample_rate * fade_ms / 1000))
    if fade_len <= 0:
        return frames
    for index in range(fade_len):
        samples[index] = int(samples[index] * (index / fade_len))
    return struct.pack("<" + "h" * len(samples), *samples)


def wav_basic_stats(path: Path) -> dict[str, object]:
    with wave.open(str(path), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        duration = wav.getnframes() / sample_rate
    if sample_width != 2 or not frames:
        return {
            "duration_seconds": round(duration, 3),
            "sample_rate": sample_rate,
            "channels": channels,
            "rms": None,
            "peak": None,
        }
    samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
    rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
    peak = max(abs(sample) for sample in samples)
    clipped = sum(1 for sample in samples if abs(sample) >= 32760)
    return {
        "duration_seconds": round(duration, 3),
        "sample_rate": sample_rate,
        "channels": channels,
        "rms": round(rms, 1),
        "peak": peak,
        "clip_ratio": round(clipped / len(samples), 6),
    }
