from __future__ import annotations

from dataclasses import replace

from app.audio import file_service
from app.core.config import load_settings


def test_warmup_builds_asr_engines_without_emotion(monkeypatch) -> None:
    built: list[str] = []
    monkeypatch.setattr(
        file_service,
        "build_default_file_asr_engines",
        lambda: built.append("asr") or [],
    )
    monkeypatch.setattr(
        file_service,
        "load_settings",
        lambda: replace(load_settings(), audio_emotion_enabled=False),
    )

    file_service.warmup_audio_pipeline()

    assert built == ["asr"]


def test_warmup_analyzes_probe_when_emotion_enabled(monkeypatch) -> None:
    analyzed: list[str] = []

    class FakeEmotionEngine:
        def __init__(self, model: str) -> None:
            self.model = model

        def analyze_file(self, path) -> None:  # type: ignore[no-untyped-def]
            assert path.exists()
            analyzed.append(str(path))

    monkeypatch.setattr(file_service, "build_default_file_asr_engines", lambda: [])
    monkeypatch.setattr(
        file_service,
        "load_settings",
        lambda: replace(
            load_settings(),
            audio_emotion_enabled=True,
            audio_emotion_model="fake-emotion-model",
        ),
    )
    monkeypatch.setattr(
        file_service, "get_emotion_engine", lambda model: FakeEmotionEngine(model)
    )

    file_service.warmup_audio_pipeline()

    assert len(analyzed) == 1


def test_warmup_swallows_missing_models(monkeypatch) -> None:
    def boom() -> list:
        raise RuntimeError("models absent")

    monkeypatch.setattr(file_service, "build_default_file_asr_engines", boom)
    monkeypatch.setattr(file_service, "load_settings", lambda: replace(load_settings(), audio_emotion_enabled=False))

    file_service.warmup_audio_pipeline()  # must not raise
