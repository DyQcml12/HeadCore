from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.audio.model_paths import resolve_modelscope_model
from app.core.security import redact_secrets


DEFAULT_EMOTION_MODEL = "iic/emotion2vec_plus_large"

EMOTION_LABEL_MAP = {
    "angry": "angry",
    "disgusted": "disgusted",
    "fearful": "fearful",
    "happy": "happy",
    "neutral": "neutral",
    "other": "other",
    "sad": "sad",
    "surprised": "surprised",
}


@dataclass(frozen=True)
class AudioEmotionResult:
    emotion: str | None
    emotion_source: str | None
    emotion_confidence: float | None
    raw_label: str | None = None
    error: str | None = None


class Emotion2VecEngine:
    provider = "funasr"

    def __init__(
        self,
        *,
        model: str = DEFAULT_EMOTION_MODEL,
        disable_update: bool = True,
        device: str | None = None,
    ) -> None:
        self.model = model
        self.disable_update = disable_update
        self.device = device
        self._automodel: Any | None = None

    def analyze_file(self, audio_path: Path) -> AudioEmotionResult:
        if not audio_path.exists():
            raise FileNotFoundError(str(audio_path))
        try:
            model = self._load_model()
            result = model.generate(
                str(audio_path),
                granularity="utterance",
                extract_embedding=False,
            )
            return parse_emotion2vec_result(result)
        except Exception as exc:
            return AudioEmotionResult(
                emotion=None,
                emotion_source="emotion2vec",
                emotion_confidence=None,
                error=redact_secrets(str(exc)),
            )

    def _load_model(self) -> Any:
        if self._automodel is not None:
            return self._automodel
        from funasr import AutoModel

        kwargs: dict[str, Any] = {
            "model": resolve_modelscope_model(self.model),
            "disable_update": self.disable_update,
        }
        if self.device:
            kwargs["device"] = self.device
        self._automodel = AutoModel(**kwargs)
        return self._automodel


def parse_emotion2vec_result(result: Any) -> AudioEmotionResult:
    first = result[0] if isinstance(result, list) and result else result
    if not isinstance(first, dict):
        return AudioEmotionResult(
            emotion=None,
            emotion_source="emotion2vec",
            emotion_confidence=None,
            error="unexpected_emotion2vec_result",
        )
    labels = first.get("labels")
    scores = first.get("scores")
    if not isinstance(labels, list) or not isinstance(scores, list) or not labels or not scores:
        return AudioEmotionResult(
            emotion=None,
            emotion_source="emotion2vec",
            emotion_confidence=None,
            error="missing_emotion2vec_labels_or_scores",
        )
    best_index = max(range(min(len(labels), len(scores))), key=lambda index: float(scores[index]))
    raw_label = str(labels[best_index])
    return AudioEmotionResult(
        emotion=normalize_emotion_label(raw_label),
        emotion_source="emotion2vec",
        emotion_confidence=float(scores[best_index]),
        raw_label=raw_label,
    )


def normalize_emotion_label(raw_label: str) -> str | None:
    lower = raw_label.strip().lower()
    if "/" in lower:
        lower = lower.rsplit("/", 1)[-1]
    return EMOTION_LABEL_MAP.get(lower)
