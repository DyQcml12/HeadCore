from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.providers.contracts import (
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderId,
    TtsRequest,
)


class VoiceReplyTtsProvider:
    capabilities = frozenset({ProviderCapability.TTS})

    def __init__(
        self,
        provider_id: str,
        synthesize: Callable[..., Any],
        options: Mapping[str, Any],
    ) -> None:
        self.provider_id = ProviderId(provider_id)
        self._synthesize = synthesize
        self._options = dict(options)

    async def synthesize(self, request: TtsRequest) -> Path:
        try:
            result = await asyncio.to_thread(
                self._synthesize,
                user_input=request.user_input or request.text,
                reply_text=request.text,
                output_dir=request.output_path.parent,
                provider=self.provider_id.value,
                **self._options,
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise _map_tts_error(exc) from exc
        send_path = getattr(result, "send_path", None)
        if not isinstance(send_path, Path):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE, "TTS result has no send path")
        return send_path


class GptSoVitsTtsProvider(VoiceReplyTtsProvider):
    def __init__(self, synthesize: Callable[..., Any], options: Mapping[str, Any]) -> None:
        super().__init__("gpt_sovits", synthesize, options)


def normalize_tts_provider_id(value: str) -> ProviderId:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"gpt_sovits", "gptsovits"}:
        return ProviderId("gpt_sovits")
    return ProviderId(normalized)


def _map_tts_error(exc: Exception) -> ProviderError:
    message = str(exc)
    normalized = message.lower()
    if "missing" in normalized or "not configured" in normalized:
        return ProviderError(ProviderErrorCode.NOT_CONFIGURED, message)
    if "http 401" in normalized or "http 403" in normalized:
        return ProviderError(ProviderErrorCode.AUTHENTICATION_FAILED, message)
    if "http 429" in normalized:
        return ProviderError(ProviderErrorCode.RATE_LIMITED, message)
    if "empty audio" in normalized or "no audio" in normalized or "instead of audio" in normalized:
        return ProviderError(ProviderErrorCode.INVALID_RESPONSE, message)
    if isinstance(exc, TimeoutError) or "timed out" in normalized or "timeout" in normalized:
        return ProviderError(ProviderErrorCode.TIMEOUT, message)
    return ProviderError(ProviderErrorCode.UNAVAILABLE, message)
