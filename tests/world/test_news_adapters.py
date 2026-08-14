from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app.core.config import load_settings
from app.world.adapters.news import GdeltNewsAdapter, GovCnPolicyAdapter, OfficialRssNewsAdapter
from app.world.contracts import WorldQuery, WorldSourceCapability
from app.world.errors import WorldSourceError, WorldSourceErrorCode
from app.world.runtime import build_world_runtime
from app.world.source_manifest import WorldSourceCatalogEntry, load_source_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeResponse:
    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        content: bytes | None = None,
        status_code: int = 200,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content if content is not None else json.dumps(payload or {}).encode()

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str], float]] = []

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.requests.append((url, params, timeout))
        return self.response


def _entry(source_id: str) -> WorldSourceCatalogEntry:
    manifest = load_source_manifest(PROJECT_ROOT / "data" / "world" / "sources.json")
    return next(item for item in manifest.sources if item.source_id == source_id)


def test_gdelt_normalizes_discovery_items_without_fetching_articles() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                payload={
                    "articles": [
                        {
                            "title": "Policy update",
                            "url": "https://news.example/item?id=1&utm_source=test#part",
                            "seendate": "20260717T030000Z",
                            "domain": "news.example",
                            "language": "English",
                            "sourcecountry": "United Kingdom",
                        },
                        {
                            "title": "Duplicate",
                            "url": "https://news.example/item?id=1&utm_source=other",
                        },
                    ]
                }
            )
        )
        adapter = GdeltNewsAdapter(
            replace(_entry("gdelt-doc"), legal_approved=True),
            client=client,
            enabled=True,
        )
        batch = await adapter.fetch(
            WorldQuery(
                source_id="gdelt-doc",
                capability=WorldSourceCapability.NEWS,
                parameters={"topic": "policy", "limit": "10"},
            )
        )
        items = batch.observations[0].payload["items"]

        assert len(items) == 1
        assert items[0]["url"] == "https://news.example/item?id=1"
        assert items[0]["published_at"] == "2026-07-17T03:00:00+00:00"
        assert client.requests[0][1]["mode"] == "artlist"
        assert client.requests[0][1]["maxrecords"] == "10"
        assert len(client.requests) == 1

    asyncio.run(scenario())


def test_rss_normalizes_html_and_rejects_nonallowlisted_item_links() -> None:
    async def scenario() -> None:
        feed = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>Health policy</title><link>https://news.un.org/en/story/1?utm_source=x</link>
    <description><![CDATA[<p>Public <b>health</b> update.</p>]]></description>
    <pubDate>Fri, 17 Jul 2026 03:00:00 GMT</pubDate></item>
  <item><title>Foreign link</title><link>https://example.com/story/2</link></item>
</channel></rss>"""
        client = FakeHttpClient(FakeResponse(content=feed))
        adapter = OfficialRssNewsAdapter(
            replace(_entry("un-news-en-rss"), legal_approved=True),
            client=client,
            enabled=True,
        )
        batch = await adapter.fetch(
            WorldQuery(
                source_id="un-news-en-rss",
                capability=WorldSourceCapability.NEWS,
                parameters={"topic": "health", "limit": "5"},
            )
        )
        items = batch.observations[0].payload["items"]

        assert len(items) == 1
        assert items[0]["summary"] == "Public health update."
        assert items[0]["url"] == "https://news.un.org/en/story/1"
        assert items[0]["published_at"] == "2026-07-17T03:00:00+00:00"
        assert client.requests[0][1] == {}

    asyncio.run(scenario())


def test_news_adapter_enforces_item_limit_and_response_size() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(FakeResponse(payload={"articles": []}))
        adapter = GdeltNewsAdapter(
            replace(_entry("gdelt-doc"), legal_approved=True),
            client=client,
            enabled=True,
            max_response_bytes=4,
        )
        with pytest.raises(WorldSourceError) as captured:
            await adapter.fetch(
                WorldQuery(
                    source_id="gdelt-doc",
                    capability=WorldSourceCapability.NEWS,
                    parameters={"topic": "policy", "limit": "51"},
                )
            )
        assert captured.value.code == WorldSourceErrorCode.INVALID_REQUEST
        assert client.requests == []

        with pytest.raises(WorldSourceError) as captured:
            await adapter.fetch(
                WorldQuery(
                    source_id="gdelt-doc",
                    capability=WorldSourceCapability.NEWS,
                    parameters={"topic": "policy", "limit": "10"},
                )
            )
        assert captured.value.code == WorldSourceErrorCode.RESPONSE_TOO_LARGE

    asyncio.run(scenario())


def test_gov_policy_adapter_uses_metadata_json_and_filters_off_host_links() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                payload=[
                    {
                        "URL": "https://www.gov.cn/zhengce/content/202607/content_1.htm?utm_source=x",
                        "TITLE": "国务院关于公共健康规划的通知",
                        "DOCRELPUBTIME": "2026-07-13",
                    },
                    {
                        "URL": "https://example.com/copied-policy",
                        "TITLE": "非白名单链接",
                        "DOCRELPUBTIME": "2026-07-12",
                    },
                ]
            )
        )
        adapter = GovCnPolicyAdapter(
            replace(
                _entry("gov-cn-policy"),
                legal_approved=True,
                automation_policy="approved_page",
            ),
            client=client,
            enabled=True,
        )
        batch = await adapter.fetch(
            WorldQuery(
                source_id="gov-cn-policy",
                capability=WorldSourceCapability.POLICY,
                parameters={"topic": "健康", "limit": "10"},
            )
        )
        items = batch.observations[0].payload["items"]

        assert len(items) == 1
        assert items[0]["url"] == "https://www.gov.cn/zhengce/content/202607/content_1.htm"
        assert items[0]["published_at"] == "2026-07-13T00:00:00+00:00"
        assert items[0]["summary"] == ""
        assert client.requests[0][0].endswith("/zhengce/zuixin/ZUIXINZHENGCE.json")
        assert len(client.requests) == 1

    asyncio.run(scenario())


def test_world_runtime_registers_supported_news_sources_but_keeps_them_disabled() -> None:
    async def scenario() -> None:
        settings = replace(load_settings(), world_awareness_enabled=False)
        runtime = build_world_runtime(settings)
        status = runtime.status()

        assert status.news_catalog_count == 8
        assert status.news_registered_count == 3
        assert status.news_enabled_count == 0
        assert status.policy_registered_count == 1
        assert status.policy_enabled_count == 0
        with pytest.raises(WorldSourceError) as captured:
            await runtime.news("gdelt-doc", topic="policy")
        assert captured.value.code == WorldSourceErrorCode.SOURCE_DISABLED
        with pytest.raises(WorldSourceError) as captured:
            await runtime.policy_updates(topic="健康")
        assert captured.value.code == WorldSourceErrorCode.SOURCE_DISABLED

    asyncio.run(scenario())


def test_world_runtime_applies_env_source_gates_without_editing_manifest() -> None:
    settings = replace(
        load_settings(),
        world_awareness_enabled=True,
        world_source_enabled_ids="gdelt-doc",
        world_source_legal_approved_ids="gdelt-doc",
    )

    status = build_world_runtime(settings).status()

    assert status.news_enabled_count == 1
    assert status.policy_enabled_count == 0


def test_world_runtime_rejects_unknown_env_source_ids() -> None:
    settings = replace(
        load_settings(),
        world_source_enabled_ids="not-in-manifest",
    )

    with pytest.raises(ValueError, match="unknown world source ids"):
        build_world_runtime(settings)
