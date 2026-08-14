from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.providers.contracts import (
    ProviderCapability,
    ProviderError,
    ProviderErrorCode,
    ProviderId,
    TextRequest,
)


class ChatClient(Protocol):
    async def chat(self, system_prompt: str, user_prompt: str) -> str: ...

    def stream_chat(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]: ...


class DeepSeekTextProvider:
    provider_id = ProviderId("deepseek")
    capabilities = frozenset({ProviderCapability.TEXT})

    def __init__(self, client: ChatClient) -> None:
        self._client = client

    async def generate_text(self, request: TextRequest) -> str:
        try:
            text = await self._client.chat(request.system_prompt, request.user_prompt)
        except ProviderError:
            raise
        except Exception as exc:
            raise _map_deepseek_error(exc) from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE, "DeepSeek returned empty text")
        return text.strip()

    async def stream_text(self, request: TextRequest) -> AsyncIterator[str]:
        try:
            async for chunk in self._client.stream_chat(request.system_prompt, request.user_prompt):
                if isinstance(chunk, str) and chunk:
                    yield chunk
        except ProviderError:
            raise
        except Exception as exc:
            raise _map_deepseek_error(exc) from exc


def _map_deepseek_error(exc: Exception) -> ProviderError:
    message = str(exc)
    normalized = message.lower()
    if "deepseek_api_key" in normalized or "not configured" in normalized:
        return ProviderError(ProviderErrorCode.NOT_CONFIGURED, message)
    if "status=401" in normalized or "status=403" in normalized:
        return ProviderError(ProviderErrorCode.AUTHENTICATION_FAILED, message)
    if "status=429" in normalized:
        return ProviderError(ProviderErrorCode.RATE_LIMITED, message)
    if "no choices" in normalized or "content is empty" in normalized:
        return ProviderError(ProviderErrorCode.INVALID_RESPONSE, message)
    return ProviderError(ProviderErrorCode.UNAVAILABLE, message)
