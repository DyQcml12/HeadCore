from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.audio.schemas import AsrEvent


class FileAsrEngine(Protocol):
    provider: str
    model: str

    def transcribe_file(self, audio_path: Path) -> str:
        pass


class StreamingAsrEngine(Protocol):
    provider: str
    model: str

    async def start(self, *, sample_rate: int, language: str, mode: str) -> None:
        pass

    async def accept_audio(self, pcm: bytes) -> list[AsrEvent]:
        pass

    async def finish(self) -> list[AsrEvent]:
        pass
