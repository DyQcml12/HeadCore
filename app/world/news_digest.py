from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.world.cache import AsyncTTLCache
from app.world.contracts import WorldAcquisitionResult
from app.world.errors import WorldSourceError, WorldSourceErrorCode

_MAX_TOPIC_LENGTH = 200
_MAX_SOURCES = 10
_MAX_ITEMS = 100


class NewsAcquirer(Protocol):
    async def news(
        self,
        source_id: str,
        *,
        topic: str = "",
        limit: int = 20,
    ) -> WorldAcquisitionResult: ...


@dataclass(frozen=True)
class NewsDigestItem:
    title: str
    urls: tuple[str, ...]
    published_at: str
    summary: str
    source_ids: tuple[str, ...]
    source_names: tuple[str, ...]
    languages: tuple[str, ...]
    source_countries: tuple[str, ...]


@dataclass(frozen=True)
class NewsDigestSourceStatus:
    source_id: str
    success: bool
    error_code: str = ""
    source_cache_hit: bool = False
    source_shared_request: bool = False
    item_count: int = 0


@dataclass(frozen=True)
class NewsDigest:
    topic: str
    generated_at: datetime
    items: tuple[NewsDigestItem, ...]
    sources: tuple[NewsDigestSourceStatus, ...]


@dataclass(frozen=True)
class NewsDigestResult:
    digest: NewsDigest
    cache_hit: bool
    shared_request: bool
    cache_key: str


class NewsDigestService:
    def __init__(
        self,
        acquirer: NewsAcquirer,
        *,
        cache: AsyncTTLCache[NewsDigest] | None = None,
        ttl_seconds: int = 300,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("news digest ttl_seconds must be positive")
        self._acquirer = acquirer
        self._cache = cache or AsyncTTLCache()
        self._ttl_seconds = ttl_seconds

    async def build(
        self,
        *,
        topic: str,
        source_ids: tuple[str, ...],
        per_source_limit: int = 20,
        max_items: int = 30,
    ) -> NewsDigestResult:
        normalized_topic = topic.strip()
        normalized_sources = tuple(
            sorted({source_id.strip().lower() for source_id in source_ids if source_id.strip()})
        )
        if len(normalized_topic) > _MAX_TOPIC_LENGTH:
            raise ValueError("news digest topic is too long")
        if not normalized_sources or len(normalized_sources) > _MAX_SOURCES:
            raise ValueError("news digest requires between 1 and 10 sources")
        if not 1 <= per_source_limit <= 50:
            raise ValueError("news digest per_source_limit must be between 1 and 50")
        if not 1 <= max_items <= _MAX_ITEMS:
            raise ValueError("news digest max_items must be between 1 and 100")

        cache_key = _digest_cache_key(
            topic=normalized_topic,
            source_ids=normalized_sources,
            per_source_limit=per_source_limit,
            max_items=max_items,
        )

        async def load() -> NewsDigest:
            return await self._build_uncached(
                topic=normalized_topic,
                source_ids=normalized_sources,
                per_source_limit=per_source_limit,
                max_items=max_items,
            )

        loaded = await self._cache.get_or_load(
            cache_key,
            ttl_seconds=self._ttl_seconds,
            loader=load,
        )
        return NewsDigestResult(
            digest=loaded.value,
            cache_hit=loaded.cache_hit,
            shared_request=loaded.shared_request,
            cache_key=cache_key,
        )

    async def _build_uncached(
        self,
        *,
        topic: str,
        source_ids: tuple[str, ...],
        per_source_limit: int,
        max_items: int,
    ) -> NewsDigest:
        results = await asyncio.gather(
            *(
                self._acquirer.news(source_id, topic=topic, limit=per_source_limit)
                for source_id in source_ids
            ),
            return_exceptions=True,
        )
        source_statuses: list[NewsDigestSourceStatus] = []
        raw_items: list[tuple[str, dict[str, object]]] = []
        for source_id, result in zip(source_ids, results, strict=True):
            if isinstance(result, BaseException):
                code = (
                    result.code.value
                    if isinstance(result, WorldSourceError)
                    else WorldSourceErrorCode.UNAVAILABLE.value
                )
                source_statuses.append(
                    NewsDigestSourceStatus(
                        source_id=source_id,
                        success=False,
                        error_code=code,
                    )
                )
                continue
            observation = result.batch.observations[0]
            items = observation.payload.get("items", [])
            safe_items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
            source_statuses.append(
                NewsDigestSourceStatus(
                    source_id=source_id,
                    success=True,
                    source_cache_hit=result.cache_hit,
                    source_shared_request=result.shared_request,
                    item_count=len(safe_items),
                )
            )
            raw_items.extend((source_id, item) for item in safe_items)

        merged = _merge_items(raw_items)
        return NewsDigest(
            topic=topic,
            generated_at=datetime.now(UTC),
            items=tuple(merged[:max_items]),
            sources=tuple(source_statuses),
        )


def _digest_cache_key(
    *,
    topic: str,
    source_ids: tuple[str, ...],
    per_source_limit: int,
    max_items: int,
) -> str:
    canonical = json.dumps(
        {
            "topic": topic,
            "sources": source_ids,
            "per_source_limit": per_source_limit,
            "max_items": max_items,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"world:news-digest:{digest}"


def _merge_items(raw_items: list[tuple[str, dict[str, object]]]) -> list[NewsDigestItem]:
    groups: dict[str, dict[str, object]] = {}
    url_to_key: dict[str, str] = {}
    for source_id, item in raw_items:
        title = _string(item.get("title"))
        url = _string(item.get("url"))
        if not title or not url:
            continue
        title_key = _normalized_title(title)
        key = url_to_key.get(url) or f"title:{title_key}"
        group = groups.get(key)
        if group is None:
            group = {
                "title": title,
                "urls": set(),
                "published_at": "",
                "summary": "",
                "source_ids": set(),
                "source_names": set(),
                "languages": set(),
                "source_countries": set(),
            }
            groups[key] = group
        cast_urls = group["urls"]
        assert isinstance(cast_urls, set)
        cast_urls.add(url)
        url_to_key[url] = key
        _add(group, "source_ids", source_id)
        _add(group, "source_names", _string(item.get("source_name")))
        _add(group, "languages", _string(item.get("language")))
        _add(group, "source_countries", _string(item.get("source_country")))
        published_at = _string(item.get("published_at"))
        if published_at > _string(group.get("published_at")):
            group["published_at"] = published_at
        summary = _string(item.get("summary"))
        if len(summary) > len(_string(group.get("summary"))):
            group["summary"] = summary

    merged: list[NewsDigestItem] = []
    for group in groups.values():
        merged.append(
            NewsDigestItem(
                title=_string(group["title"]),
                urls=_sorted_strings(group["urls"]),
                published_at=_string(group["published_at"]),
                summary=_string(group["summary"]),
                source_ids=_sorted_strings(group["source_ids"]),
                source_names=_sorted_strings(group["source_names"]),
                languages=_sorted_strings(group["languages"]),
                source_countries=_sorted_strings(group["source_countries"]),
            )
        )
    merged.sort(key=lambda item: (item.published_at, item.title), reverse=True)
    return merged


def _normalized_title(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold())


def _add(group: dict[str, object], field: str, value: str) -> None:
    if not value:
        return
    target = group[field]
    assert isinstance(target, set)
    target.add(value)


def _sorted_strings(value: object) -> tuple[str, ...]:
    assert isinstance(value, set)
    return tuple(sorted(item for item in value if isinstance(item, str) and item))


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""
