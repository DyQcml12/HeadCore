from __future__ import annotations

import asyncio

import pytest

from app.providers import ProviderError, ProviderErrorCode, TextRequest
from app.providers.deepseek import DeepSeekTextProvider


class StubClient:
    def __init__(self, outcome: str | Exception) -> None:
        self.outcome = outcome

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_deepseek_adapter_returns_trimmed_text() -> None:
    provider = DeepSeekTextProvider(StubClient("  reply  "))

    result = asyncio.run(provider.generate_text(TextRequest("system", "user")))

    assert result == "reply"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("DEEPSEEK_API_KEY is not configured.", ProviderErrorCode.NOT_CONFIGURED),
        ("request failed: status=401", ProviderErrorCode.AUTHENTICATION_FAILED),
        ("request failed: status=429", ProviderErrorCode.RATE_LIMITED),
        ("Model response has no choices.", ProviderErrorCode.INVALID_RESPONSE),
        ("connection refused", ProviderErrorCode.UNAVAILABLE),
    ],
)
def test_deepseek_adapter_maps_existing_client_errors(message: str, expected: ProviderErrorCode) -> None:
    provider = DeepSeekTextProvider(StubClient(RuntimeError(message)))

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.generate_text(TextRequest("system", "user")))

    assert caught.value.code is expected

