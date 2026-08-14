from __future__ import annotations

from app.audio.asr_engine import StreamingAsrEngine
from app.audio.schemas import AsrEvent


class AsrStreamSession:
    def __init__(self, engine: StreamingAsrEngine) -> None:
        self.engine = engine
        self.started = False

    async def start(self, *, sample_rate: int, language: str, mode: str) -> list[AsrEvent]:
        await self.engine.start(sample_rate=sample_rate, language=language, mode=mode)
        self.started = True
        return []

    async def accept_audio(self, pcm: bytes) -> list[AsrEvent]:
        if not self.started:
            return [
                AsrEvent(
                    type="error",
                    text="ASR stream has not started.",
                    is_final=True,
                )
            ]
        return await self.engine.accept_audio(pcm)

    async def finish(self) -> list[AsrEvent]:
        if not self.started:
            return []
        return await self.engine.finish()
