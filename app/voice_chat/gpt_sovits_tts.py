from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path


def synthesize_gpt_sovits(
    *,
    base_url: str,
    text: str,
    output_path: Path,
    ref_audio_path: str,
    prompt_text: str,
    prompt_lang: str = "zh",
    text_lang: str = "zh",
    top_k: int = 15,
    top_p: float = 0.85,
    temperature: float = 0.70,
    text_split_method: str = "cut5",
    batch_size: int = 1,
    speed_factor: float = 0.93,
    fragment_interval: float = 0.25,
    seed: int = 1856666206,
    parallel_infer: bool = True,
    repetition_penalty: float = 1.20,
    timeout_seconds: int = 180,
) -> int:
    """Call a local GPT-SoVITS api_v2 /tts endpoint and persist its WAV response."""
    reference_path = Path(ref_audio_path).expanduser().resolve()
    if not reference_path.is_file():
        raise FileNotFoundError(f"GPT-SoVITS reference audio not found: {reference_path}")
    payload = {
        "text": text,
        "text_lang": text_lang,
        "ref_audio_path": str(reference_path),
        "prompt_text": prompt_text,
        "prompt_lang": prompt_lang,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "text_split_method": text_split_method,
        "batch_size": batch_size,
        "speed_factor": speed_factor,
        "fragment_interval": fragment_interval,
        "seed": seed,
        "parallel_infer": parallel_infer,
        "repetition_penalty": repetition_penalty,
        "media_type": "wav",
        "streaming_mode": False,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/tts",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "Accept": "audio/wav, audio/*"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GPT-SoVITS HTTP {exc.code}: {message[-500:]}") from exc
    if "audio" not in content_type.lower() or len(body) <= 44 or body[:4] != b"RIFF":
        message = body.decode("utf-8", errors="replace")
        raise RuntimeError(f"GPT-SoVITS synthesis returned invalid audio: {message[-500:]}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(body)
    return len(body)


def check_gpt_sovits_ready(base_url: str, timeout_seconds: int = 5) -> bool:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/openapi.json", timeout=timeout_seconds) as response:
            schema = json.loads(response.read().decode("utf-8"))
        return "/tts" in schema.get("paths", {})
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return False
