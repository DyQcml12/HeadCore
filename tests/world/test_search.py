from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.world.adapters.search import WebSearchAdapter
from app.world.brain import WorldBrainCoordinator, WorldToolIntent, decide_world_tools
from app.world.context import WorldContextAssembler
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldQuery,
    WorldSourceCapability,
)
from app.world.tool_request import TOOL_CAPABILITY_SEARCH, parse_tool_request


def _search_result() -> WorldAcquisitionResult:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    observation = WorldObservation(
        observation_id="web-search:web_search:demo",
        capability=WorldSourceCapability.WEB_SEARCH,
        observed_at=now,
        expires_at=now + timedelta(seconds=300),
        confidence=0.7,
        payload={
            "query": "量子计算",
            "items": [
                {
                    "title": "量子计算新进展",
                    "url": "https://example.com/a",
                    "snippet": "一条摘要",
                    "published_at": "",
                    "source_name": "example.com",
                }
            ],
        },
        evidence=(WorldEvidence("web-search", "https://api.tavily.com/search", now, "d" * 64),),
        sensitivity=DataSensitivity.PUBLIC,
    )
    return WorldAcquisitionResult(
        batch=WorldObservationBatch("web-search", WorldSourceCapability.WEB_SEARCH, now, (observation,)),
        cache_hit=False,
        shared_request=False,
        cache_key="world:web-search:web_search:demo",
    )


class _SearchRuntime:
    def status(self):
        class Status:
            enabled = True

        return Status()

    async def search(self, query: str, *, limit: int = 6):
        return _search_result()


def test_decide_world_tools_recognizes_search() -> None:
    decision = decide_world_tools("帮我搜索一下量子计算最新进展")

    assert decision.intent == WorldToolIntent.WEB_SEARCH
    assert decision.reason_code == "explicit_search_request"
    assert decision.topic == "量子计算最新进展"
    assert decision.requires_location is False


def test_parse_tool_request_recognizes_search() -> None:
    request = parse_tool_request("[USE_WORLD_TOOL:搜索:量子计算]")

    assert request is not None
    assert request.capability == TOOL_CAPABILITY_SEARCH
    assert request.query == "量子计算"
    assert request.as_user_query() == "搜索 量子计算"


def test_search_adapter_fetches_via_tavily_and_builds_batch(monkeypatch) -> None:
    async def fake_tavily(**kwargs):
        return [
            {
                "title": "结果一",
                "url": "https://example.com/a",
                "snippet": "摘要",
                "published_at": "",
                "source_name": "example.com",
            }
        ]

    monkeypatch.setattr("app.world.adapters.search._tavily_search", fake_tavily)
    adapter = WebSearchAdapter(provider="tavily", api_key="k", enabled=True, legal_approved=True)

    batch = asyncio.run(
        adapter.fetch(
            WorldQuery(
                source_id="web-search",
                capability=WorldSourceCapability.WEB_SEARCH,
                parameters={"query": "x"},
            )
        )
    )

    observation = batch.observations[0]
    assert observation.capability == WorldSourceCapability.WEB_SEARCH
    items = observation.payload["items"]
    assert items[0]["title"] == "结果一"


def test_public_url_strips_tracking_and_credentials() -> None:
    from app.world.adapters.search import _public_url

    assert _public_url("https://example.com/a?utm_source=x&fbclid=y") == "https://example.com/a"
    assert _public_url("https://user:pass@example.com/a") == ""
    assert _public_url("javascript:alert(1)") == ""


def test_search_adapter_falls_back_to_duckduckgo_without_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.world.adapters.search._duckduckgo_results",
        lambda query, limit: [{"title": "D", "url": "https://d.example", "snippet": "", "published_at": "", "source_name": "d.example"}],
    )
    adapter = WebSearchAdapter(provider="tavily", api_key="", enabled=True, legal_approved=True)

    batch = asyncio.run(
        adapter.fetch(
            WorldQuery(
                source_id="web-search",
                capability=WorldSourceCapability.WEB_SEARCH,
                parameters={"query": "x"},
            )
        )
    )

    assert batch.observations[0].payload["items"][0]["title"] == "D"


def test_from_search_renders_items() -> None:
    projection = WorldContextAssembler().from_search(_search_result(), tool_intent="web_search")

    assert projection.status == "ready"
    assert "量子计算新进展" in projection.rendered_text
    assert projection.item_count == 1


def test_search_returns_no_persistable_results() -> None:
    async def scenario() -> None:
        coordinator = WorldBrainCoordinator(_SearchRuntime())
        result = await coordinator.build_context_with_evidence("帮我搜索量子计算")

        assert result.projection.status == "ready"
        assert result.persistable_results == ()

    asyncio.run(scenario())
