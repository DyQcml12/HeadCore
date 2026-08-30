from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.world.contracts import (
    DataSensitivity,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldQuery,
    WorldSourceCapability,
    WorldSourceDefinition,
    WorldSourceKind,
)
from app.world.errors import WorldSourceError, WorldSourceErrorCode

_SEARCH_SOURCE_ID = "web-search"
_TAVILY_URL = "https://api.tavily.com/search"
_MAX_QUERY_LENGTH = 200
_MAX_ITEM_LIMIT = 10
_MAX_SNIPPET_LENGTH = 1000
_TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})


class WebSearchAdapter:
    """General-purpose realtime web search.

    Tavily (with an API key) is the primary backend; DuckDuckGo (via the optional
    ``ddgs`` package, no key) is the fallback. Search results are only projected
    into the current turn and cached in memory for a short TTL — they are never
    turned into persisted cognitive facts or graph updates by the caller.
    """

    def __init__(
        self,
        *,
        provider: str = "tavily",
        api_key: str = "",
        enabled: bool = False,
        legal_approved: bool = False,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 1_048_576,
        max_results: int = 6,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("search timeout_seconds must be positive")
        if max_response_bytes <= 0:
            raise ValueError("search max_response_bytes must be positive")
        if not 1 <= max_results <= _MAX_ITEM_LIMIT:
            raise ValueError(f"search max_results must be between 1 and {_MAX_ITEM_LIMIT}")
        self._provider = provider.strip().lower()
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_results = max_results
        self.definition = WorldSourceDefinition(
            source_id=_SEARCH_SOURCE_ID,
            kind=WorldSourceKind.API,
            capabilities=frozenset({WorldSourceCapability.WEB_SEARCH}),
            enabled=enabled,
            legal_approved=legal_approved,
            terms_url="https://tavily.com/terms-of-use",
            allowed_hosts=(),
        )

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch:
        if query.source_id != _SEARCH_SOURCE_ID or query.capability != WorldSourceCapability.WEB_SEARCH:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        query_text = query.parameters.get("query", "").strip()
        if not query_text or len(query_text) > _MAX_QUERY_LENGTH:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        limit = _query_limit(query, self._max_results)
        items = await self._run_search(query_text, limit)
        return _search_batch(query, items)

    async def _run_search(self, query_text: str, limit: int) -> list[dict[str, str]]:
        if self._provider == "tavily" and self._api_key:
            try:
                return await _tavily_search(
                    api_key=self._api_key,
                    query=query_text,
                    limit=limit,
                    timeout_seconds=self._timeout_seconds,
                    max_response_bytes=self._max_response_bytes,
                )
            except WorldSourceError:
                # Fall through to the no-key DuckDuckGo backend.
                pass
        return _duckduckgo_results(query_text, limit)


def _query_limit(query: WorldQuery, default: int) -> int:
    raw = query.parameters.get("limit", str(default))
    try:
        limit = int(raw)
    except ValueError as exc:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST) from exc
    if not 1 <= limit <= _MAX_ITEM_LIMIT:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
    return limit


async def _tavily_search(
    *,
    api_key: str,
    query: str,
    limit: int,
    timeout_seconds: float,
    max_response_bytes: int,
) -> list[dict[str, str]]:
    import httpx

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": limit,
        "search_depth": "basic",
        "include_answer": False,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(_TAVILY_URL, json=payload)
    except TimeoutError as exc:
        raise WorldSourceError(WorldSourceErrorCode.TIMEOUT) from exc
    except Exception as exc:
        raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE) from exc
    _validate_response(response.status_code, response.content, max_response_bytes)
    try:
        data = response.json()
    except Exception as exc:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE) from exc
    if not isinstance(data, dict):
        raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
    items: list[dict[str, str]] = []
    for raw in data.get("results", []):
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title"), limit=500)
        url = _public_url(raw.get("url"))
        snippet = _text(raw.get("content") or raw.get("snippet") or "", limit=_MAX_SNIPPET_LENGTH)
        if not title or not url:
            continue
        items.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "published_at": "",
                "source_name": urlparse(url).hostname or "",
            }
        )
        if len(items) >= limit:
            break
    return items


def _duckduckgo_results(query: str, limit: int) -> list[dict[str, str]]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise WorldSourceError(
            WorldSourceErrorCode.NOT_CONFIGURED,
            "DuckDuckGo search requires the optional 'ddgs' package",
        ) from exc

    items: list[dict[str, str]] = []
    try:
        with DDGS() as ddgs:
            for raw in ddgs.text(query, max_results=limit):
                title = _text(raw.get("title"), limit=500)
                url = _public_url(raw.get("href") or raw.get("url"))
                snippet = _text(raw.get("body") or raw.get("snippet") or "", limit=_MAX_SNIPPET_LENGTH)
                if not title or not url:
                    continue
                items.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "published_at": "",
                        "source_name": urlparse(url).hostname or "",
                    }
                )
                if len(items) >= limit:
                    break
    except WorldSourceError:
        raise
    except Exception as exc:
        raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE) from exc
    return items


def _search_batch(query: WorldQuery, items: list[dict[str, str]]) -> WorldObservationBatch:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {"query": query.parameters.get("query", "").strip(), "items": items}
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    evidence = WorldEvidence(
        source_id=_SEARCH_SOURCE_ID,
        source_uri=_TAVILY_URL,
        retrieved_at=now,
        content_hash=digest,
        license_id="web-search-metadata",
    )
    observation = WorldObservation(
        observation_id=f"{_SEARCH_SOURCE_ID}:{query.capability.value}:{digest[:24]}",
        capability=query.capability,
        observed_at=now,
        expires_at=now + timedelta(seconds=query.ttl_seconds),
        confidence=0.7,
        payload=payload,
        evidence=(evidence,),
        sensitivity=DataSensitivity.PUBLIC,
    )
    return WorldObservationBatch(
        source_id=_SEARCH_SOURCE_ID,
        capability=query.capability,
        fetched_at=now,
        observations=(observation,),
    )


def _validate_response(status_code: int, content: bytes, max_response_bytes: int) -> None:
    if len(content) > max_response_bytes:
        raise WorldSourceError(WorldSourceErrorCode.RESPONSE_TOO_LARGE)
    if status_code in {401, 403}:
        raise WorldSourceError(WorldSourceErrorCode.AUTHENTICATION_FAILED)
    if status_code == 429:
        raise WorldSourceError(WorldSourceErrorCode.RATE_LIMITED)
    if status_code >= 500:
        raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE)
    if status_code != 200:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _public_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_PARAMETERS and not key.lower().startswith("utm_")
        ],
        doseq=True,
    )
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", query, ""))
