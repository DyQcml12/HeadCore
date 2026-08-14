from __future__ import annotations

import hashlib
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.voice_chat.audio_utils import append_wav_files
from app.voice_chat.gpt_sovits_tts import check_gpt_sovits_ready, synthesize_gpt_sovits
from app.voice_chat.naturalness import normalize_text_for_tts
from app.voice_chat.planner import load_reference_library, plan_voice_chat


@dataclass(frozen=True)
class VoiceSynthesisResult:
    wav_path: Path
    send_path: Path
    emotion: str
    text: str


def should_request_voice_reply(text: str) -> bool:
    normalized = text.strip()
    explicit_markers = [
        "发语音",
        "发个语音",
        "发一段语音",
        "来段语音",
        "来个语音",
        "语音回复",
        "用语音",
        "说句话",
        "说一声",
        "念出来",
        "读出来",
        "开口说",
        "声音给我听",
        "声音听听",
        "听听你的声音",
        "语音我听听",
        "听你说",
    ]
    if any(marker in normalized for marker in explicit_markers):
        return True
    if "声音" in normalized and any(marker in normalized for marker in ["听", "说", "发", "给我"]):
        return True
    if "想听" in normalized and any(marker in normalized for marker in ["你", "胡桃", "现在", "就想听"]):
        return True
    return False


def _prefer_explicit(
    explicit_value: int | float,
    segment_value: int | float | None,
    default: int | float,
) -> int | float:
    """Use a caller-passed value when it differs from the default, else the planned one."""
    if explicit_value != default:
        return explicit_value
    if segment_value is None:
        return explicit_value
    return segment_value


def synthesize_voice_reply(
    *,
    user_input: str,
    reply_text: str,
    output_dir: Path,
    base_url: str,
    provider: str = "gpt_sovits",
    ffmpeg_path: str = "ffmpeg",
    send_format: str = "mp3",
    timeout_seconds: int = 180,
    gpt_sovits_ref_audio_path: str = "",
    gpt_sovits_prompt_text: str = "",
    gpt_sovits_prompt_lang: str = "zh",
    gpt_sovits_text_lang: str = "zh",
    gpt_sovits_top_k: int = 15,
    gpt_sovits_top_p: float = 0.85,
    gpt_sovits_temperature: float = 0.70,
    gpt_sovits_repetition_penalty: float = 1.20,
    gpt_sovits_speed_factor: float = 0.93,
    gpt_sovits_fragment_interval: float = 0.25,
    gpt_sovits_text_split_method: str = "cut5",
    gpt_sovits_batch_size: int = 1,
    gpt_sovits_seed: int = 1856666206,
    gpt_sovits_parallel_infer: bool = True,
) -> VoiceSynthesisResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_reply = normalize_text_for_tts(reply_text)
    plan = plan_voice_chat(user_input, normalized_reply)
    if not plan.segments:
        raise ValueError("voice plan has no segments")
    stem = build_voice_file_stem(user_input=user_input, reply_text=normalized_reply)
    wav_path = output_dir / f"{stem}.wav"
    segment_paths = []
    normalized_provider = normalize_voice_provider(provider)
    for segment in plan.segments:
        segment_stem = f"{stem}_segment_{segment.index}"
        segment_path = output_dir / f"{segment_stem}.wav"
        segment_paths.append(segment_path)
        if normalized_provider == "gpt_sovits":
            reference = segment.reference
            segment_params = dict(segment.generation_params)
            synthesize_gpt_sovits(
                base_url=base_url,
                text=segment.text,
                output_path=segment_path,
                ref_audio_path=gpt_sovits_ref_audio_path or reference.audio_path,
                prompt_text=gpt_sovits_prompt_text or reference.prompt_text,
                prompt_lang=gpt_sovits_prompt_lang,
                text_lang=gpt_sovits_text_lang,
                top_k=_prefer_explicit(gpt_sovits_top_k, segment_params.get("top_k"), 15),
                top_p=_prefer_explicit(gpt_sovits_top_p, segment_params.get("top_p"), 0.85),
                temperature=_prefer_explicit(gpt_sovits_temperature, segment_params.get("temperature"), 0.70),
                repetition_penalty=_prefer_explicit(
                    gpt_sovits_repetition_penalty, segment_params.get("repetition_penalty"), 1.20
                ),
                speed_factor=_prefer_explicit(gpt_sovits_speed_factor, segment_params.get("speed_factor"), 0.93),
                fragment_interval=gpt_sovits_fragment_interval,
                text_split_method=gpt_sovits_text_split_method,
                batch_size=gpt_sovits_batch_size,
                seed=gpt_sovits_seed,
                parallel_infer=gpt_sovits_parallel_infer,
                timeout_seconds=timeout_seconds,
            )
        else:
            raise ValueError(f"Unsupported voice provider: {provider}")
    if len(segment_paths) == 1:
        wav_path = segment_paths[0]
    elif segment_paths:
        append_wav_files(
            segment_paths,
            wav_path,
            pause_ms=[segment.pause_after_ms for segment in plan.segments],
        )
    send_path = wav_path
    if send_format.lower() == "mp3":
        send_path = wav_path.with_suffix(".mp3")
        convert_audio_for_delivery(wav_path=wav_path, output_path=send_path, ffmpeg_path=ffmpeg_path)
    return VoiceSynthesisResult(
        wav_path=wav_path,
        send_path=send_path,
        emotion=plan.emotion,
        text=normalized_reply,
    )


def convert_audio_for_delivery(*, wav_path: Path, output_path: Path, ffmpeg_path: str = "ffmpeg") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(wav_path),
        "-vn",
        "-ar",
        "24000",
        "-ac",
        "1",
        "-b:a",
        "96k",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg convert failed: " + (result.stderr or result.stdout)[-500:])


def build_voice_file_stem(*, user_input: str, reply_text: str) -> str:
    digest = hashlib.sha256((user_input + "\n" + reply_text).encode("utf-8")).hexdigest()[:16]
    return f"hutao_voice_{digest}"


def check_tts_api_ready(base_url: str, timeout_seconds: int = 5) -> bool:
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + "/control?" + urllib.parse.urlencode({"command": "none"}),
            timeout=timeout_seconds,
        ):
            return True
    except Exception:
        return False


def check_voice_provider_ready(
    *,
    provider: str,
    base_url: str,
    timeout_seconds: int = 5,
) -> bool:
    normalized_provider = normalize_voice_provider(provider)
    if normalized_provider == "gpt_sovits":
        return check_gpt_sovits_ready(base_url, timeout_seconds=timeout_seconds)
    raise ValueError(f"Unsupported voice provider: {provider}")


def normalize_voice_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("-", "_")
    if normalized in {"gpt_sovits", "gptsovits"}:
        return "gpt_sovits"
    raise ValueError(f"Unsupported voice provider: {provider}")


DEFAULT_VOICE_OUTPUT_DIR = PROJECT_ROOT / "data" / "generated_voice"
