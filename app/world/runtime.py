from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from app.core.config import Settings
from app.world.adapters.amap import AmapWorldSourceAdapter
from app.world.adapters.news import GdeltNewsAdapter, GovCnPolicyAdapter, OfficialRssNewsAdapter
from app.world.adapters.qweather import QweatherWeatherAdapter
from app.world.adapters.search import WebSearchAdapter
from app.world.cache import AsyncTTLCache
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldObservationBatch,
    WorldQuery,
    WorldSourceCapability,
)
from app.world.http import AsyncHttpClient
from app.world.news_digest import NewsDigestResult, NewsDigestService
from app.world.registry import WorldSourceRegistry
from app.world.service import WorldAcquisitionService
from app.world.source_manifest import load_source_manifest


@dataclass(frozen=True)
class WorldRuntimeStatus:
    enabled: bool
    amap_registered: bool
    amap_key_configured: bool
    amap_legal_approved: bool
    qweather_registered: bool
    qweather_key_configured: bool
    qweather_legal_approved: bool
    news_catalog_count: int
    news_registered_count: int
    news_enabled_count: int
    policy_registered_count: int
    policy_enabled_count: int
    search_registered: bool
    search_enabled: bool
    search_key_configured: bool


class WorldRuntime:
    def __init__(
        self,
        service: WorldAcquisitionService,
        settings: Settings,
        *,
        news_ttl_by_source: dict[str, int] | None = None,
        news_catalog_count: int = 0,
        news_registered_count: int = 0,
        news_enabled_count: int = 0,
        policy_registered_count: int = 0,
        policy_enabled_count: int = 0,
    ) -> None:
        self._service = service
        self._settings = settings
        self._news_ttl_by_source = news_ttl_by_source or {}
        self._news_catalog_count = news_catalog_count
        self._news_registered_count = news_registered_count
        self._news_enabled_count = news_enabled_count
        self._policy_registered_count = policy_registered_count
        self._policy_enabled_count = policy_enabled_count
        self._news_digest_service = NewsDigestService(
            self,
            cache=AsyncTTLCache(max_entries=settings.world_cache_max_entries),
        )

    def status(self) -> WorldRuntimeStatus:
        return WorldRuntimeStatus(
            enabled=self._settings.world_awareness_enabled,
            amap_registered=True,
            amap_key_configured=bool(self._settings.amap_web_service_api_key),
            amap_legal_approved=self._settings.amap_source_legal_approved,
            qweather_registered=True,
            qweather_key_configured=bool(self._settings.qweather_api_key),
            qweather_legal_approved=self._settings.qweather_source_legal_approved,
            news_catalog_count=self._news_catalog_count,
            news_registered_count=self._news_registered_count,
            news_enabled_count=self._news_enabled_count,
            policy_registered_count=self._policy_registered_count,
            policy_enabled_count=self._policy_enabled_count,
            search_registered=True,
            search_enabled=self._settings.world_awareness_enabled and self._settings.web_search_enabled,
            search_key_configured=bool(self._settings.web_search_api_key),
        )

    async def locate_public_ip(
        self,
        ip: str,
        *,
        consent_granted: bool,
    ) -> WorldAcquisitionResult:
        return await self._service.acquire(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.IP_LOCATION,
                parameters={"ip": ip},
                ttl_seconds=self._settings.amap_ip_cache_ttl_seconds,
                sensitivity=DataSensitivity.COARSE_LOCATION,
                consent_granted=consent_granted,
                cache_partition="coarse-location",
            )
        )

    async def current_weather(self, location: str) -> WorldAcquisitionResult:
        return await self._service.acquire(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.WEATHER_CURRENT,
                parameters={"adcode": location},
                ttl_seconds=self._settings.amap_weather_cache_ttl_seconds,
                cache_partition="public-weather",
            )
        )

    async def weather_forecast(self, location: str) -> WorldAcquisitionResult:
        return await self._service.acquire(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.WEATHER_FORECAST,
                parameters={"adcode": location},
                ttl_seconds=self._settings.amap_weather_cache_ttl_seconds,
                cache_partition="public-weather",
            )
        )

    async def resolve_district(self, keyword: str) -> WorldAcquisitionResult:
        return await self._service.acquire(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.MAP_PLACE,
                parameters={"operation": "district", "keyword": keyword},
                ttl_seconds=self._settings.amap_district_cache_ttl_seconds,
                cache_partition="public-district",
            )
        )

    async def search_places(
        self,
        keyword: str,
        *,
        city: str = "",
        limit: int = 5,
    ) -> WorldAcquisitionResult:
        return await self._service.acquire(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.MAP_PLACE,
                parameters={
                    "operation": "place",
                    "keyword": keyword,
                    "city": city,
                    "limit": str(limit),
                },
                ttl_seconds=self._settings.amap_place_cache_ttl_seconds,
                sensitivity=DataSensitivity.PRECISE_LOCATION,
                cache_partition="map-place",
            )
        )

    async def route(
        self,
        origin: str,
        destination: str,
        *,
        mode: str,
        origin_city: str = "",
        destination_city: str = "",
        consent_granted: bool,
    ) -> WorldAcquisitionResult:
        return await self._service.acquire(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.MAP_ROUTE,
                parameters={
                    "origin": origin,
                    "destination": destination,
                    "mode": mode,
                    "city": origin_city,
                    "destination_city": destination_city,
                },
                ttl_seconds=self._settings.amap_route_cache_ttl_seconds,
                sensitivity=DataSensitivity.PRECISE_LOCATION,
                consent_granted=consent_granted,
                cache_partition="precise-route",
            )
        )

    async def news(
        self,
        source_id: str,
        *,
        topic: str = "",
        limit: int = 20,
    ) -> WorldAcquisitionResult:
        ttl_seconds = self._news_ttl_by_source.get(source_id.strip().lower(), 900)
        return await self._service.acquire(
            WorldQuery(
                source_id=source_id,
                capability=WorldSourceCapability.NEWS,
                parameters={"topic": topic, "limit": str(limit)},
                ttl_seconds=ttl_seconds,
                cache_partition="public-news",
            )
        )

    async def policy_updates(
        self,
        source_id: str = "gov-cn-policy",
        *,
        topic: str = "",
        limit: int = 20,
    ) -> WorldAcquisitionResult:
        ttl_seconds = self._news_ttl_by_source.get(source_id.strip().lower(), 1800)
        return await self._service.acquire(
            WorldQuery(
                source_id=source_id,
                capability=WorldSourceCapability.POLICY,
                parameters={"topic": topic, "limit": str(limit)},
                ttl_seconds=ttl_seconds,
                cache_partition="public-policy",
            )
        )

    async def news_digest(
        self,
        *,
        topic: str,
        source_ids: tuple[str, ...],
        per_source_limit: int = 20,
        max_items: int = 30,
    ) -> NewsDigestResult:
        return await self._news_digest_service.build(
            topic=topic,
            source_ids=source_ids,
            per_source_limit=per_source_limit,
            max_items=max_items,
        )

    async def search(
        self,
        query: str,
        *,
        limit: int = 6,
    ) -> WorldAcquisitionResult:
        return await self._service.acquire(
            WorldQuery(
                source_id="web-search",
                capability=WorldSourceCapability.WEB_SEARCH,
                parameters={"query": query, "limit": str(limit)},
                ttl_seconds=self._settings.web_search_cache_ttl_seconds,
                cache_partition="public-search",
            )
        )


def build_world_runtime(
    settings: Settings,
    *,
    http_client: AsyncHttpClient | None = None,
) -> WorldRuntime:
    registry = WorldSourceRegistry()
    allowed_hosts = tuple(
        host.strip() for host in settings.amap_allowed_hosts.split(",") if host.strip()
    )
    registry.register(
        AmapWorldSourceAdapter(
            api_key=settings.amap_web_service_api_key,
            client=http_client,
            base_url=settings.amap_web_service_base_url,
            allowed_hosts=allowed_hosts,
            enabled=settings.world_awareness_enabled,
            legal_approved=settings.amap_source_legal_approved,
            timeout_seconds=settings.world_fetch_timeout_seconds,
            max_response_bytes=settings.world_fetch_max_bytes,
        )
    )
    qweather_hosts = tuple(
        host.strip() for host in settings.qweather_allowed_hosts.split(",") if host.strip()
    )
    registry.register(
        QweatherWeatherAdapter(
            api_key=settings.qweather_api_key,
            client=http_client,
            base_url=settings.qweather_api_base_url,
            allowed_hosts=qweather_hosts,
            enabled=settings.world_awareness_enabled,
            legal_approved=settings.qweather_source_legal_approved,
            timeout_seconds=settings.world_fetch_timeout_seconds,
            max_response_bytes=settings.world_fetch_max_bytes,
        )
    )
    registry.register(
        WebSearchAdapter(
            provider=settings.web_search_provider,
            api_key=settings.web_search_api_key,
            enabled=settings.world_awareness_enabled and settings.web_search_enabled,
            legal_approved=settings.web_search_enabled,
            timeout_seconds=settings.world_fetch_timeout_seconds,
            max_response_bytes=settings.world_fetch_max_bytes,
            max_results=settings.web_search_max_results,
        )
    )
    manifest_path = Path(settings.world_official_source_manifest)
    if not manifest_path.is_absolute():
        manifest_path = Path(__file__).resolve().parents[2] / manifest_path
    manifest = load_source_manifest(manifest_path)
    enabled_source_ids = _configured_source_ids(settings.world_source_enabled_ids)
    approved_source_ids = _configured_source_ids(
        settings.world_source_legal_approved_ids
    )
    catalog_source_ids = {entry.source_id for entry in manifest.sources}
    unknown_source_ids = (enabled_source_ids | approved_source_ids) - catalog_source_ids
    if unknown_source_ids:
        raise ValueError(
            "unknown world source ids: " + ", ".join(sorted(unknown_source_ids))
        )
    news_ttl_by_source: dict[str, int] = {}
    news_registered_count = 0
    news_enabled_count = 0
    policy_registered_count = 0
    policy_enabled_count = 0
    for entry in manifest.sources:
        entry = replace(
            entry,
            enabled=entry.enabled or entry.source_id in enabled_source_ids,
            legal_approved=(
                entry.legal_approved or entry.source_id in approved_source_ids
            ),
        )
        adapter = None
        enabled = settings.world_awareness_enabled and entry.enabled
        if entry.source_id == "gdelt-doc":
            adapter = GdeltNewsAdapter(
                entry,
                client=http_client,
                enabled=enabled,
                timeout_seconds=settings.world_fetch_timeout_seconds,
                max_response_bytes=settings.world_fetch_max_bytes,
            )
        elif entry.kind.value == "rss":
            adapter = OfficialRssNewsAdapter(
                entry,
                client=http_client,
                enabled=enabled,
                timeout_seconds=settings.world_fetch_timeout_seconds,
                max_response_bytes=settings.world_fetch_max_bytes,
            )
        elif entry.source_id == "gov-cn-policy":
            adapter = GovCnPolicyAdapter(
                entry,
                client=http_client,
                enabled=enabled,
                timeout_seconds=settings.world_fetch_timeout_seconds,
                max_response_bytes=settings.world_fetch_max_bytes,
            )
        if adapter is None:
            continue
        registry.register(adapter)
        news_ttl_by_source[entry.source_id] = entry.refresh_seconds
        if entry.source_id == "gov-cn-policy":
            policy_registered_count += 1
            policy_enabled_count += int(enabled and entry.legal_approved)
        else:
            news_registered_count += 1
            news_enabled_count += int(enabled and entry.legal_approved)
    unbacked_source_ids = (enabled_source_ids | approved_source_ids) - set(news_ttl_by_source)
    if unbacked_source_ids:
        raise ValueError(
            "world sources configured but not backed by an adapter: "
            + ", ".join(sorted(unbacked_source_ids))
        )
    cache: AsyncTTLCache[WorldObservationBatch] = AsyncTTLCache(
        max_entries=settings.world_cache_max_entries
    )
    service = WorldAcquisitionService(
        registry,
        cache,
        max_ttl_seconds=settings.world_max_cache_ttl_seconds,
    )
    return WorldRuntime(
        service,
        settings,
        news_ttl_by_source=news_ttl_by_source,
        news_catalog_count=len(manifest.sources),
        news_registered_count=news_registered_count,
        news_enabled_count=news_enabled_count,
        policy_registered_count=policy_registered_count,
        policy_enabled_count=policy_enabled_count,
    )


def _configured_source_ids(raw: str) -> set[str]:
    return {value.strip().lower() for value in raw.split(",") if value.strip()}
