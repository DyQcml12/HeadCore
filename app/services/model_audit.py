from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.core.security import redact_secrets


DEFAULT_AUDIT_LOG_PATH = PROJECT_ROOT / "logs" / "model-invocations" / "model-invocations.jsonl"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModelInvocationAuditRecord:
    timestamp: str
    provider: str
    model: str
    used_live_api: bool
    fallback_used: bool
    latency_ms: float
    prompt_hash: str
    response_hash: str
    error: str | None = None


class ModelInvocationAuditLogger:
    def __init__(self, path: Path = DEFAULT_AUDIT_LOG_PATH) -> None:
        self.path = path

    def write(
        self,
        *,
        provider: str,
        model: str,
        used_live_api: bool,
        fallback_used: bool,
        latency_ms: float,
        prompt_text: str,
        response_text: str,
        error: str | None,
    ) -> ModelInvocationAuditRecord:
        record = ModelInvocationAuditRecord(
            timestamp=dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds"),
            provider=provider,
            model=model,
            used_live_api=used_live_api,
            fallback_used=fallback_used,
            latency_ms=round(latency_ms, 2),
            prompt_hash=text_hash(prompt_text),
            response_hash=text_hash(response_text),
            error=redact_secrets(error) if error else None,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record
