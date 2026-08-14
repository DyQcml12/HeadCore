from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.audio.model_paths import resolve_funasr_aux_model, resolve_modelscope_model


DEFAULT_FUNASR_MODEL = "iic/SenseVoiceSmall"
FUNASR_NANO_MODEL = "FunAudioLLM/Fun-ASR-Nano-2512"
PARAFORMER_ZH_MODEL = "paraformer-zh"
DEFAULT_FUNASR_VAD_MODEL = "fsmn-vad"
DEFAULT_FUNASR_PUNC_MODEL = "ct-punc"

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "sensevoice-small": {
        "model": DEFAULT_FUNASR_MODEL,
        "vad_model": DEFAULT_FUNASR_VAD_MODEL,
        "punc_model": DEFAULT_FUNASR_PUNC_MODEL,
        "language": "zh",
        "generate_kwargs": {"use_itn": True, "batch_size_s": 60},
    },
    "fun-asr-nano": {
        "model": FUNASR_NANO_MODEL,
        "vad_model": DEFAULT_FUNASR_VAD_MODEL,
        "punc_model": DEFAULT_FUNASR_PUNC_MODEL,
        "language": "中文",
        "trust_remote_code": True,
        "remote_code": "./model.py",
        "generate_kwargs": {"itn": True, "batch_size": 1},
    },
    "paraformer-zh": {
        "model": PARAFORMER_ZH_MODEL,
        "vad_model": DEFAULT_FUNASR_VAD_MODEL,
        "punc_model": DEFAULT_FUNASR_PUNC_MODEL,
        "language": "zh",
        "generate_kwargs": {"use_itn": True, "batch_size_s": 60},
    },
}


class FunAsrUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class AsrTranscriptionResult:
    text: str
    emotion: str | None = None
    emotion_source: str | None = None
    emotion_confidence: float | None = None


class FunAsrFileEngine:
    provider = "funasr"

    def __init__(
        self,
        *,
        model: str = DEFAULT_FUNASR_MODEL,
        vad_model: str | None = DEFAULT_FUNASR_VAD_MODEL,
        punc_model: str | None = DEFAULT_FUNASR_PUNC_MODEL,
        device: str = "cuda:0",
        disable_update: bool = True,
        language: str = "zh",
        trust_remote_code: bool = False,
        remote_code: str | None = None,
        generate_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.vad_model = vad_model
        self.punc_model = punc_model
        self.device = device
        self.disable_update = disable_update
        self.language = language
        self.trust_remote_code = trust_remote_code
        self.remote_code = remote_code
        self.generate_kwargs = generate_kwargs or {"use_itn": True, "batch_size_s": 60}
        self._automodel: Any | None = None

    @classmethod
    def from_preset(
        cls,
        preset: str,
        *,
        device: str = "cuda:0",
        disable_update: bool = True,
    ) -> "FunAsrFileEngine":
        if preset not in MODEL_PRESETS:
            raise ValueError(f"Unknown FunASR preset: {preset}")
        config = MODEL_PRESETS[preset]
        return cls(
            model=str(config["model"]),
            vad_model=config.get("vad_model"),  # type: ignore[arg-type]
            punc_model=config.get("punc_model"),  # type: ignore[arg-type]
            device=device,
            disable_update=disable_update,
            language=str(config.get("language", "zh")),
            trust_remote_code=bool(config.get("trust_remote_code", False)),
            remote_code=config.get("remote_code"),  # type: ignore[arg-type]
            generate_kwargs=dict(config.get("generate_kwargs", {})),
        )

    def transcribe_file(self, audio_path: Path) -> AsrTranscriptionResult:
        if not audio_path.exists():
            raise FileNotFoundError(str(audio_path))
        model = self._load_model()
        generate_kwargs = dict(self.generate_kwargs)
        result = model.generate(
            input=str(audio_path),
            cache={},
            language=self.language,
            **generate_kwargs,
            merge_vad=True,
            merge_length_s=15,
        )
        return extract_transcription_result(result)

    def _load_model(self) -> Any:
        if self._automodel is not None:
            return self._automodel
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise FunAsrUnavailableError(
                "FunASR is not installed. Install it before running real ASR tests."
            ) from exc
        kwargs: dict[str, Any] = {
            "model": resolve_modelscope_model(self.model),
            "device": self.device,
            "disable_update": self.disable_update,
            "trust_remote_code": self.trust_remote_code,
        }
        if self.remote_code:
            kwargs["remote_code"] = self.remote_code
        if self.vad_model:
            kwargs["vad_model"] = resolve_funasr_aux_model(self.vad_model)
        if self.punc_model:
            kwargs["punc_model"] = resolve_funasr_aux_model(self.punc_model)
        self._automodel = AutoModel(**kwargs)
        return self._automodel


SENSEVOICE_EMOTION_MAP = {
    "NEUTRAL": "neutral",
    "HAPPY": "happy",
    "SAD": "sad",
    "ANGRY": "angry",
    "FEARFUL": "fearful",
    "DISGUSTED": "disgusted",
    "SURPRISED": "surprised",
}


def extract_transcription_result(result: Any) -> AsrTranscriptionResult:
    raw_text = extract_raw_text(result)
    emotion = extract_sensevoice_emotion(raw_text)
    return AsrTranscriptionResult(
        text=clean_asr_text(raw_text),
        emotion=emotion,
        emotion_source="sensevoice_tag" if emotion else None,
        emotion_confidence=None,
    )


def extract_text(result: Any) -> str:
    return extract_transcription_result(result).text


def extract_raw_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return str(result.get("text", ""))
    if isinstance(result, list):
        parts = [extract_raw_text(item) for item in result]
        return "".join(part for part in parts if part)
    return str(result)


def extract_sensevoice_emotion(text: str) -> str | None:
    for tag in re.findall(r"<\s*\|\s*([^|]*?)\s*\|\s*>", text):
        normalized = tag.strip().upper()
        if normalized in SENSEVOICE_EMOTION_MAP:
            return SENSEVOICE_EMOTION_MAP[normalized]
    return None


def clean_asr_text(text: str) -> str:
    cleaned = re.sub(r"<\s*\|\s*[^|]*\s*\|\s*>", "", text)
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"([。！？!?，,、])\1+", r"\1", cleaned)
    return cleaned.strip()
