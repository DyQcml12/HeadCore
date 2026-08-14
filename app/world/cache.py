from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class CacheLoadResult(Generic[T]):
    value: T
    cache_hit: bool
    shared_request: bool


@dataclass(frozen=True)
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class AsyncTTLCache(Generic[T]):
    def __init__(
        self,
        *,
        max_entries: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("cache max_entries must be positive")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[str, _CacheEntry[T]] = {}
        self._inflight: dict[str, asyncio.Task[T]] = {}
        self._lock = asyncio.Lock()

    async def get_or_load(
        self,
        key: str,
        *,
        ttl_seconds: int,
        loader: Callable[[], Awaitable[T]],
    ) -> CacheLoadResult[T]:
        if not key:
            raise ValueError("cache key must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("cache ttl_seconds must be positive")

        async with self._lock:
            now = self._clock()
            self._remove_expired(now)
            cached = self._entries.get(key)
            if cached is not None:
                return CacheLoadResult(cached.value, cache_hit=True, shared_request=False)

            task = self._inflight.get(key)
            owner = task is None
            if task is None:
                task = asyncio.create_task(loader())
                self._inflight[key] = task

        try:
            value = await asyncio.shield(task)
        except BaseException:
            if owner:
                async with self._lock:
                    self._inflight.pop(key, None)
            raise

        if owner:
            async with self._lock:
                self._inflight.pop(key, None)
                self._remove_expired(self._clock())
                if len(self._entries) >= self._max_entries:
                    oldest_key = min(
                        self._entries,
                        key=lambda existing_key: self._entries[existing_key].expires_at,
                    )
                    self._entries.pop(oldest_key, None)
                self._entries[key] = _CacheEntry(
                    value=value,
                    expires_at=self._clock() + ttl_seconds,
                )
        return CacheLoadResult(value, cache_hit=False, shared_request=not owner)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()

    def _remove_expired(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)
