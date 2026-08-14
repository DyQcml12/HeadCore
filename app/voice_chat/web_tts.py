from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass


class WebVoiceReplyNotFoundError(Exception):
    pass


class WebVoiceReplyBusyError(Exception):
    pass


class WebVoiceReplyRateLimitError(Exception):
    pass


@dataclass(frozen=True)
class WebVoiceReply:
    reply_id: str
    user_id: str
    session_id: str
    text: str
    expires_at: float


class WebVoiceReplyStore:
    def __init__(
        self,
        *,
        reply_ttl_seconds: int,
        min_interval_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if reply_ttl_seconds < 1 or min_interval_seconds < 0:
            raise ValueError("web voice timing configuration is invalid")
        self._reply_ttl_seconds = reply_ttl_seconds
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._replies: dict[str, WebVoiceReply] = {}
        self._active_reply_ids: dict[str, str] = {}
        self._last_started_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def new_reply_id(self) -> str:
        return secrets.token_urlsafe(24)

    async def remember(
        self,
        *,
        user_id: str,
        session_id: str,
        text: str,
        reply_id: str | None = None,
    ) -> str:
        normalized_text = text.strip()
        if not user_id.strip() or not session_id.strip() or not normalized_text:
            raise ValueError("web voice reply is invalid")
        now = self._clock()
        async with self._lock:
            self._purge_expired(now)
            resolved_reply_id = reply_id or self.new_reply_id()
            while resolved_reply_id in self._replies:
                if reply_id is not None:
                    raise ValueError("web voice reply id already exists")
                resolved_reply_id = self.new_reply_id()
            self._replies[resolved_reply_id] = WebVoiceReply(
                reply_id=resolved_reply_id,
                user_id=user_id,
                session_id=session_id,
                text=normalized_text,
                expires_at=now + self._reply_ttl_seconds,
            )
            return resolved_reply_id

    async def acquire(self, reply_id: str, *, user_id: str, session_id: str) -> WebVoiceReply:
        now = self._clock()
        async with self._lock:
            self._purge_expired(now)
            reply = self._replies.get(reply_id)
            if reply is None or reply.user_id != user_id or reply.session_id != session_id:
                raise WebVoiceReplyNotFoundError("web voice reply not found")
            if user_id in self._active_reply_ids.values():
                raise WebVoiceReplyBusyError("web voice reply is already synthesizing")
            last_started_at = self._last_started_at.get(user_id)
            if last_started_at is not None and now - last_started_at < self._min_interval_seconds:
                raise WebVoiceReplyRateLimitError("web voice request rate exceeded")
            self._active_reply_ids[reply_id] = user_id
            self._last_started_at[user_id] = now
            return reply

    async def release(self, reply_id: str) -> None:
        async with self._lock:
            self._active_reply_ids.pop(reply_id, None)

    def _purge_expired(self, now: float) -> None:
        expired_ids = [reply_id for reply_id, reply in self._replies.items() if reply.expires_at <= now]
        for reply_id in expired_ids:
            self._replies.pop(reply_id, None)
            self._active_reply_ids.pop(reply_id, None)
