from __future__ import annotations

import json
import asyncio
import hashlib
import threading
from typing import Any
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.security import redact_secrets


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._http_client: httpx.AsyncClient | None = None
        self._http_client_loop: asyncio.AbstractEventLoop | None = None
        self._client_lock = threading.Lock()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Reuse keep-alive connections while remaining safe across test loops."""
        loop = asyncio.get_running_loop()
        old_client: httpx.AsyncClient | None = None
        with self._client_lock:
            client = self._http_client
            if client is None or client.is_closed or self._http_client_loop is not loop:
                old_client = client
                timeout = max(float(self.settings.request_timeout_seconds), 0.1)
                self._http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        timeout=timeout,
                        connect=min(timeout, 10.0),
                        read=timeout,
                        write=min(timeout, 15.0),
                        pool=min(timeout, 10.0),
                    ),
                    limits=httpx.Limits(
                        max_connections=100,
                        max_keepalive_connections=20,
                        keepalive_expiry=30.0,
                    ),
                )
                self._http_client_loop = loop
            client = self._http_client
        if old_client is not None and old_client is not client:
            await old_client.aclose()
        assert client is not None
        return client

    async def aclose(self) -> None:
        with self._client_lock:
            client = self._http_client
            self._http_client = None
            self._http_client_loop = None
        if client is not None and not client.is_closed:
            await client.aclose()

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured.")
        payload = {
            "model": self.settings.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        client = await self._get_http_client()
        response = await client.post(
            self.settings.chat_completions_url,
            json=payload,
            headers=headers,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = redact_secrets(response.text[:1200])
            raise RuntimeError(
                f"DeepSeek request failed: status={exc.response.status_code}; body={body}"
            ) from exc
        return self._extract_text(response.json())

    async def stream_chat(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured.")
        payload = {
            "model": self.settings.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        client = await self._get_http_client()
        async with client.stream(
            "POST",
            self.settings.chat_completions_url,
            json=payload,
            headers=headers,
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = redact_secrets((await response.aread()).decode("utf-8", errors="ignore")[:1200])
                raise RuntimeError(
                    f"DeepSeek stream request failed: status={exc.response.status_code}; body={body}"
                ) from exc
            async for line in response.aiter_lines():
                chunk = self._extract_stream_delta(line)
                if chunk:
                    yield chunk

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("Model response has no choices.")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Model response content is empty.")
        return content.strip()

    @staticmethod
    def _extract_stream_delta(line: str) -> str:
        stripped = line.strip()
        if not stripped or not stripped.startswith("data:"):
            return ""
        payload = stripped.removeprefix("data:").strip()
        if payload == "[DONE]":
            return ""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("model stream sent a non-JSON data frame") from exc
        if not isinstance(data, dict):
            raise RuntimeError("model stream sent a non-object data frame")
        if "error" in data:
            raise RuntimeError(
                "model stream returned an error frame: "
                + redact_secrets(str(data.get("error")))[:600]
            )
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("model stream data frame has no choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError("model stream choice is not an object")
        delta = first.get("delta")
        if not isinstance(delta, dict):
            return ""
        content = delta.get("content")
        return content if isinstance(content, str) else ""


_SHARED_CLIENTS: dict[tuple[str, str, str, float, float], DeepSeekClient] = {}
_SHARED_CLIENTS_LOCK = threading.Lock()


def get_shared_deepseek_client(settings: Settings) -> DeepSeekClient:
    """Return one connection-pooling client for the current model settings."""
    key_digest = hashlib.sha256(settings.deepseek_api_key.encode("utf-8")).hexdigest()
    key = (
        settings.model_base_url.rstrip("/"),
        settings.model_name,
        key_digest,
        float(settings.request_timeout_seconds),
        float(settings.temperature),
    )
    with _SHARED_CLIENTS_LOCK:
        client = _SHARED_CLIENTS.get(key)
        if client is None:
            client = DeepSeekClient(settings)
            _SHARED_CLIENTS[key] = client
        return client


async def close_shared_deepseek_clients() -> None:
    with _SHARED_CLIENTS_LOCK:
        clients = tuple(_SHARED_CLIENTS.values())
        _SHARED_CLIENTS.clear()
    await asyncio.gather(*(client.aclose() for client in clients), return_exceptions=True)
