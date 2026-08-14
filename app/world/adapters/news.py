from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.parse import urljoin

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
from app.world.http import AsyncHttpClient, HttpResponse
from app.world.source_manifest import WorldSourceCatalogEntry

_MAX_TOPIC_LENGTH = 200
_MAX_ITEM_LIMIT = 50
_MAX_SUMMARY_LENGTH = 1000
_TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})


class GdeltNewsAdapter:
    def __init__(
        self,
        entry: WorldSourceCatalogEntry,
        *,
        client: AsyncHttpClient | None = None,
        enabled: bool = False,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        _validate_news_entry(entry, expected_kind=WorldSourceKind.API)
        if entry.source_id != "gdelt-doc":
            raise ValueError("GDELT adapter requires the gdelt-doc source")
        _validate_limits(timeout_seconds, max_response_bytes)
        self.definition = _definition(entry, enabled=enabled)
        self._entry = entry
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch:
        _validate_news_query(query, self.definition.source_id)
        topic = query.parameters.get("topic", "").strip()
        if not topic or len(topic) > _MAX_TOPIC_LENGTH:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        limit = _query_limit(query)
        response = await _get(
            client=self._client,
            url=self._entry.entry_url,
            params={
                "query": topic,
                "mode": "artlist",
                "maxrecords": str(limit),
                "format": "json",
                "sort": "hybridrel",
            },
            timeout_seconds=self._timeout_seconds,
        )
        _validate_response(response, self._max_response_bytes)
        try:
            payload = response.json()
        except Exception as exc:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("articles", []), list):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)

        items: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for raw_item in payload.get("articles", [])[:limit]:
            if not isinstance(raw_item, dict):
                continue
            title = _text(raw_item.get("title"), limit=500)
            url = _canonical_public_url(raw_item.get("url"))
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "summary": "",
                    "published_at": _gdelt_datetime(raw_item.get("seendate")),
                    "source_name": _text(raw_item.get("domain"), limit=200),
                    "source_country": _text(raw_item.get("sourcecountry"), limit=100),
                    "language": _text(raw_item.get("language"), limit=100),
                }
            )
        return _news_batch(
            definition=self.definition,
            query=query,
            payload={"topic": topic, "items": items},
            source_uri=self._entry.entry_url,
            license_id="gdelt-discovery",
            confidence=0.7,
        )


class OfficialRssNewsAdapter:
    def __init__(
        self,
        entry: WorldSourceCatalogEntry,
        *,
        client: AsyncHttpClient | None = None,
        enabled: bool = False,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        _validate_news_entry(entry, expected_kind=WorldSourceKind.RSS)
        _validate_limits(timeout_seconds, max_response_bytes)
        self.definition = _definition(entry, enabled=enabled)
        self._entry = entry
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch:
        _validate_news_query(query, self.definition.source_id)
        topic = query.parameters.get("topic", "").strip()
        if len(topic) > _MAX_TOPIC_LENGTH:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        limit = _query_limit(query)
        response = await _get(
            client=self._client,
            url=self._entry.entry_url,
            params={},
            timeout_seconds=self._timeout_seconds,
        )
        _validate_response(response, self._max_response_bytes)
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE) from exc

        items = _rss_items(
            root,
            allowed_hosts=self._entry.allowed_hosts,
            topic=topic,
            limit=limit,
        )
        return _news_batch(
            definition=self.definition,
            query=query,
            payload={"topic": topic, "items": items},
            source_uri=self._entry.entry_url,
            license_id=f"{self.definition.source_id}-feed",
            confidence=0.9,
        )


class GovCnPolicyAdapter:
    def __init__(
        self,
        entry: WorldSourceCatalogEntry,
        *,
        client: AsyncHttpClient | None = None,
        enabled: bool = False,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        if entry.source_id != "gov-cn-policy":
            raise ValueError("government policy adapter requires gov-cn-policy")
        if entry.kind != WorldSourceKind.HTTP:
            raise ValueError("government policy adapter requires an HTTP source")
        if WorldSourceCapability.POLICY not in entry.capabilities:
            raise ValueError("government policy source must declare the policy capability")
        _validate_limits(timeout_seconds, max_response_bytes)
        self.definition = WorldSourceDefinition(
            source_id=entry.source_id,
            kind=entry.kind,
            capabilities=frozenset({WorldSourceCapability.POLICY}),
            enabled=enabled,
            legal_approved=entry.legal_approved,
            terms_url=entry.terms_url,
            allowed_hosts=entry.allowed_hosts,
        )
        self._entry = entry
        self._data_url = urljoin(entry.entry_url, "ZUIXINZHENGCE.json")
        if urlparse(self._data_url).hostname not in entry.allowed_hosts:
            raise ValueError("government policy data URL host is not allowlisted")
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch:
        if (
            query.source_id != self.definition.source_id
            or query.capability != WorldSourceCapability.POLICY
        ):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        topic = query.parameters.get("topic", "").strip()
        if len(topic) > _MAX_TOPIC_LENGTH:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        limit = _query_limit(query)
        response = await _get(
            client=self._client,
            url=self._data_url,
            params={},
            timeout_seconds=self._timeout_seconds,
        )
        _validate_response(response, self._max_response_bytes)
        try:
            payload = response.json()
        except Exception as exc:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE) from exc
        if not isinstance(payload, list):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)

        normalized_topic = topic.casefold()
        items: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for raw_item in payload:
            if not isinstance(raw_item, dict):
                continue
            title = _text(raw_item.get("TITLE"), limit=500)
            url = _canonical_public_url(
                raw_item.get("URL"),
                allowed_hosts=self._entry.allowed_hosts,
            )
            if not title or not url or url in seen_urls:
                continue
            if normalized_topic and normalized_topic not in title.casefold():
                continue
            seen_urls.add(url)
            items.append(
                {
                    "title": title,
                    "url": url,
                    "summary": "",
                    "published_at": _date_only_datetime(raw_item.get("DOCRELPUBTIME")),
                    "source_name": "www.gov.cn",
                    "source_country": "China",
                    "language": "zh-CN",
                }
            )
            if len(items) >= limit:
                break
        return _news_batch(
            definition=self.definition,
            query=query,
            payload={"topic": topic, "items": items},
            source_uri=self._data_url,
            license_id="gov-cn-policy-metadata",
            confidence=0.95,
        )


def _validate_news_entry(
    entry: WorldSourceCatalogEntry,
    *,
    expected_kind: WorldSourceKind,
) -> None:
    if entry.kind != expected_kind:
        raise ValueError(f"news adapter requires a {expected_kind.value} source")
    if WorldSourceCapability.NEWS not in entry.capabilities:
        raise ValueError("news adapter source must declare the news capability")


def _definition(entry: WorldSourceCatalogEntry, *, enabled: bool) -> WorldSourceDefinition:
    return WorldSourceDefinition(
        source_id=entry.source_id,
        kind=entry.kind,
        capabilities=frozenset({WorldSourceCapability.NEWS}),
        enabled=enabled,
        legal_approved=entry.legal_approved,
        terms_url=entry.terms_url,
        allowed_hosts=entry.allowed_hosts,
    )


def _validate_limits(timeout_seconds: float, max_response_bytes: int) -> None:
    if timeout_seconds <= 0:
        raise ValueError("news timeout_seconds must be positive")
    if max_response_bytes <= 0:
        raise ValueError("news max_response_bytes must be positive")


def _validate_news_query(query: WorldQuery, source_id: str) -> None:
    if query.source_id != source_id or query.capability != WorldSourceCapability.NEWS:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)


def _query_limit(query: WorldQuery) -> int:
    raw_limit = query.parameters.get("limit", "20")
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST) from exc
    if not 1 <= limit <= _MAX_ITEM_LIMIT:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
    return limit


async def _get(
    *,
    client: AsyncHttpClient | None,
    url: str,
    params: dict[str, str],
    timeout_seconds: float,
) -> HttpResponse:
    try:
        if client is not None:
            return await client.get(url, params=params, timeout=timeout_seconds)
        import httpx

        async with httpx.AsyncClient(follow_redirects=False) as default_client:
            return await default_client.get(url, params=params, timeout=timeout_seconds)
    except TimeoutError as exc:
        raise WorldSourceError(WorldSourceErrorCode.TIMEOUT) from exc
    except WorldSourceError:
        raise
    except Exception as exc:
        if exc.__class__.__name__ in {
            "ConnectTimeout",
            "PoolTimeout",
            "ReadTimeout",
            "TimeoutException",
            "WriteTimeout",
        }:
            raise WorldSourceError(WorldSourceErrorCode.TIMEOUT) from exc
        raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE) from exc


def _validate_response(response: HttpResponse, max_response_bytes: int) -> None:
    if len(response.content) > max_response_bytes:
        raise WorldSourceError(WorldSourceErrorCode.RESPONSE_TOO_LARGE)
    if response.status_code in {401, 403}:
        raise WorldSourceError(WorldSourceErrorCode.AUTHENTICATION_FAILED)
    if response.status_code == 429:
        raise WorldSourceError(WorldSourceErrorCode.RATE_LIMITED)
    if response.status_code >= 500:
        raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE)
    if response.status_code != 200:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)


def _news_batch(
    *,
    definition: WorldSourceDefinition,
    query: WorldQuery,
    payload: dict[str, Any],
    source_uri: str,
    license_id: str,
    confidence: float,
) -> WorldObservationBatch:
    now = datetime.now(UTC)
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    evidence = WorldEvidence(
        source_id=definition.source_id,
        source_uri=source_uri,
        retrieved_at=now,
        content_hash=digest,
        license_id=license_id,
    )
    observation = WorldObservation(
        observation_id=f"{definition.source_id}:{query.capability.value}:{digest[:24]}",
        capability=query.capability,
        observed_at=now,
        expires_at=now + timedelta(seconds=query.ttl_seconds),
        confidence=confidence,
        payload=payload,
        evidence=(evidence,),
        sensitivity=DataSensitivity.PUBLIC,
    )
    return WorldObservationBatch(
        source_id=definition.source_id,
        capability=query.capability,
        fetched_at=now,
        observations=(observation,),
    )


def _rss_items(
    root: ET.Element,
    *,
    allowed_hosts: tuple[str, ...],
    topic: str,
    limit: int,
) -> list[dict[str, str]]:
    candidates = root.findall(".//item")
    atom = False
    if not candidates:
        candidates = root.findall(".//{*}entry")
        atom = True
    normalized_topic = topic.casefold()
    items: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for element in candidates:
        title = _child_text(element, "title")
        summary = _plain_text(
            _child_text(element, "summary" if atom else "description")
            or _child_text(element, "content")
        )
        raw_link = _atom_link(element) if atom else _child_text(element, "link")
        url = _canonical_public_url(raw_link, allowed_hosts=allowed_hosts)
        if not title or not url or url in seen_urls:
            continue
        if normalized_topic and normalized_topic not in f"{title} {summary}".casefold():
            continue
        seen_urls.add(url)
        raw_published = (
            _child_text(element, "published")
            or _child_text(element, "updated")
            or _child_text(element, "pubDate")
        )
        items.append(
            {
                "title": title[:500],
                "url": url,
                "summary": summary[:_MAX_SUMMARY_LENGTH],
                "published_at": _feed_datetime(raw_published),
                "source_name": urlparse(url).hostname or "",
                "source_country": "",
                "language": "",
            }
        )
        if len(items) >= limit:
            break
    return items


def _child_text(element: ET.Element, local_name: str) -> str:
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == local_name:
            return _text(child.text, limit=5000)
    return ""


def _atom_link(element: ET.Element) -> str:
    for child in element:
        if child.tag.rsplit("}", 1)[-1] != "link":
            continue
        rel = child.attrib.get("rel", "alternate")
        if rel == "alternate" and child.attrib.get("href"):
            return child.attrib["href"]
    return ""


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    parser = _HtmlTextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return ""
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _canonical_public_url(
    value: object,
    *,
    allowed_hosts: tuple[str, ...] | None = None,
) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    hostname = parsed.hostname.lower()
    if allowed_hosts is not None and hostname not in allowed_hosts:
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


def _gdelt_datetime(value: object) -> str:
    text = _text(value, limit=40)
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue
    return ""


def _feed_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _date_only_datetime(value: object) -> str:
    text = _text(value, limit=20)
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return ""


def _text(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:limit]
