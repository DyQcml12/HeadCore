from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from app.audio.emotion_engine import Emotion2VecEngine
from app.audio.funasr_engine import AsrTranscriptionResult, FunAsrFileEngine


@dataclass(frozen=True)
class EmotionEnrichedAsrEngine:
    """Adds optional emotion2vec evidence to a file ASR result."""

    engine: FunAsrFileEngine
    emotion_engine: Emotion2VecEngine | None = None

    def transcribe_file(self, path: Path) -> AsrTranscriptionResult:
        result = self.engine.transcribe_file(path)
        if self.emotion_engine is None:
            return result
        emotion = self.emotion_engine.analyze_file(path)
        if emotion.emotion is None:
            return result
        return replace(
            result,
            emotion=emotion.emotion,
            emotion_source=emotion.emotion_source,
            emotion_confidence=emotion.emotion_confidence,
        )
