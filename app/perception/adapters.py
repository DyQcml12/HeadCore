from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Protocol

from app.perception.contracts import ProviderOutput, ProviderTrace
from app.providers.contracts import ProviderError


class FileObserver(Protocol):
    provider: str
    model: str

    def observe(self, path: Path) -> Any: ...


@dataclass(frozen=True)
class AdapterResult:
    output: ProviderOutput | None
    trace: ProviderTrace


class AsrObservationAdapter:
    def __init__(self, engine: object) -> None:
        self.engine = engine
        self.provider = str(getattr(engine, "provider", "asr"))
        self.model = str(getattr(engine, "model", ""))

    def observe(self, path: Path, *, fallback: bool = False) -> AdapterResult:
        started = monotonic()
        try:
            raw = self.engine.transcribe_file(path)  # type: ignore[attr-defined]
            output = ProviderOutput.from_value(raw)
            if not output.text.strip():
                raise ValueError("ASR returned empty text")
            return AdapterResult(output, self._trace(started, fallback, True, None))
        except Exception as exc:
            return AdapterResult(None, self._trace(started, fallback, False, _error_code(exc)))

    def _trace(self, started: float, fallback: bool, success: bool, error_code: str | None) -> ProviderTrace:
        return ProviderTrace(
            provider=self.provider,
            model=self.model,
            latency_ms=(monotonic() - started) * 1000,
            fallback=fallback,
            success=success,
            error_code=error_code,
        )


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return exc.code.value
    normalized = str(exc).lower()
    if "model" in normalized and ("missing" in normalized or "not found" in normalized):
        return "model_missing"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, (TypeError, ValueError)):
        return "invalid_response"
    return "provider_unavailable"
