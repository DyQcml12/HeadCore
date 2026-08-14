from __future__ import annotations

import json
from typing import Any
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.security import redact_secrets


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
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
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
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
        except json.JSONDecodeError:
            return ""
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        delta = first.get("delta")
        if not isinstance(delta, dict):
            return ""
        content = delta.get("content")
        return content if isinstance(content, str) else ""
