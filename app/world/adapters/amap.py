from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

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


class AmapWorldSourceAdapter:
    SOURCE_ID = "amap"
    _CAPABILITIES = frozenset(
        {
            WorldSourceCapability.IP_LOCATION,
            WorldSourceCapability.WEATHER_CURRENT,
            WorldSourceCapability.WEATHER_FORECAST,
            WorldSourceCapability.MAP_PLACE,
            WorldSourceCapability.MAP_ROUTE,
        }
    )

    def __init__(
        self,
        *,
        api_key: str,
        client: AsyncHttpClient | None = None,
        base_url: str = "https://restapi.amap.com",
        allowed_hosts: tuple[str, ...] = ("restapi.amap.com",),
        enabled: bool = False,
        legal_approved: bool = False,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Amap timeout_seconds must be positive")
        if max_response_bytes <= 0:
            raise ValueError("Amap max_response_bytes must be positive")
        normalized_hosts = tuple(host.strip().lower() for host in allowed_hosts if host.strip())
        parsed = urlparse(base_url.rstrip("/"))
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Amap base_url must use https")
        if parsed.hostname.lower() not in normalized_hosts:
            raise ValueError("Amap base_url host is not allowlisted")
        self.definition = WorldSourceDefinition(
            source_id=self.SOURCE_ID,
            kind=WorldSourceKind.API,
            capabilities=self._CAPABILITIES,
            enabled=enabled,
            legal_approved=legal_approved,
            terms_url="https://lbs.amap.com/api/webservice/summary",
            allowed_hosts=normalized_hosts,
        )
        self._api_key = api_key.strip()
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch:
        if not self._api_key:
            raise WorldSourceError(WorldSourceErrorCode.NOT_CONFIGURED)
        if query.capability == WorldSourceCapability.IP_LOCATION:
            return await self._fetch_ip_location(query)
        if query.capability in {
            WorldSourceCapability.WEATHER_CURRENT,
            WorldSourceCapability.WEATHER_FORECAST,
        }:
            return await self._fetch_weather(query)
        if query.capability == WorldSourceCapability.MAP_PLACE:
            if query.parameters.get("operation", "district") == "district":
                return await self._fetch_district(query)
            return await self._fetch_place(query)
        if query.capability == WorldSourceCapability.MAP_ROUTE:
            return await self._fetch_route(query)
        raise WorldSourceError(WorldSourceErrorCode.CAPABILITY_UNSUPPORTED)

    async def _fetch_ip_location(self, query: WorldQuery) -> WorldObservationBatch:
        if not query.consent_granted:
            raise WorldSourceError(WorldSourceErrorCode.CONSENT_REQUIRED)
        raw_ip = query.parameters.get("ip", "").strip()
        try:
            parsed_ip = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST) from exc
        if parsed_ip.version != 4 or not parsed_ip.is_global:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)

        now = datetime.now(UTC)
        payload = await self._request_json("/v3/ip", {"ip": raw_ip, "output": "JSON"})
        normalized = {
            "province": _text(payload.get("province")),
            "city": _text(payload.get("city")),
            "adcode": _text(payload.get("adcode")),
        }
        if not normalized["adcode"]:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        observation = self._observation(
            capability=query.capability,
            now=now,
            ttl_seconds=query.ttl_seconds,
            payload=normalized,
            endpoint="/v3/ip",
            sensitivity=DataSensitivity.COARSE_LOCATION,
            confidence=0.65,
        )
        return WorldObservationBatch(
            source_id=self.SOURCE_ID,
            capability=query.capability,
            fetched_at=now,
            observations=(observation,),
        )

    async def _fetch_weather(self, query: WorldQuery) -> WorldObservationBatch:
        adcode = query.parameters.get("adcode", "").strip()
        if len(adcode) != 6 or not adcode.isdigit():
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        forecast = query.capability == WorldSourceCapability.WEATHER_FORECAST
        now = datetime.now(UTC)
        payload = await self._request_json(
            "/v3/weather/weatherInfo",
            {
                "city": adcode,
                "extensions": "all" if forecast else "base",
                "output": "JSON",
            },
        )
        collection_name = "forecasts" if forecast else "lives"
        records = payload.get(collection_name)
        if not isinstance(records, list) or not records or not isinstance(records[0], dict):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        record = records[0]
        normalized = (
            {
                "province": _text(record.get("province")),
                "city": _text(record.get("city")),
                "adcode": _text(record.get("adcode")),
                "report_time": _text(record.get("reporttime")),
                "casts": _normalized_casts(record.get("casts")),
            }
            if forecast
            else {
                "province": _text(record.get("province")),
                "city": _text(record.get("city")),
                "adcode": _text(record.get("adcode")),
                "weather": _text(record.get("weather")),
                "temperature_c": _text(record.get("temperature")),
                "wind_direction": _text(record.get("winddirection")),
                "wind_power": _text(record.get("windpower")),
                "humidity_percent": _text(record.get("humidity")),
                "report_time": _text(record.get("reporttime")),
            }
        )
        observation = self._observation(
            capability=query.capability,
            now=now,
            ttl_seconds=query.ttl_seconds,
            payload=normalized,
            endpoint="/v3/weather/weatherInfo",
            sensitivity=DataSensitivity.PUBLIC,
            confidence=0.8,
        )
        return WorldObservationBatch(
            source_id=self.SOURCE_ID,
            capability=query.capability,
            fetched_at=now,
            observations=(observation,),
        )

    async def _fetch_district(self, query: WorldQuery) -> WorldObservationBatch:
        keyword = query.parameters.get("keyword", "").strip()
        if (
            not keyword
            or len(keyword) > 50
            or any(ord(character) < 32 for character in keyword)
        ):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        now = datetime.now(UTC)
        payload = await self._request_json(
            "/v3/config/district",
            {
                "keywords": keyword,
                "subdistrict": "0",
                "extensions": "base",
                "page": "1",
                "offset": "20",
                "output": "JSON",
            },
        )
        records = payload.get("districts", [])
        if not isinstance(records, list):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        districts: list[dict[str, str]] = []
        for record in records[:20]:
            if not isinstance(record, dict):
                continue
            name = _text(record.get("name"))
            adcode = _text(record.get("adcode"))
            if not name or len(adcode) != 6 or not adcode.isdigit():
                continue
            districts.append(
                {
                    "name": name,
                    "adcode": adcode,
                    "citycode": _text(record.get("citycode")),
                    "level": _text(record.get("level")),
                }
            )
        observation = self._observation(
            capability=query.capability,
            now=now,
            ttl_seconds=query.ttl_seconds,
            payload={"keyword": keyword, "districts": districts},
            endpoint="/v3/config/district",
            sensitivity=DataSensitivity.PUBLIC,
            confidence=0.9,
        )
        return WorldObservationBatch(
            source_id=self.SOURCE_ID,
            capability=query.capability,
            fetched_at=now,
            observations=(observation,),
        )

    async def _fetch_place(self, query: WorldQuery) -> WorldObservationBatch:
        keyword = query.parameters.get("keyword", "").strip()
        city = query.parameters.get("city", "").strip()
        limit = _bounded_integer(query.parameters.get("limit", "5"), minimum=1, maximum=10)
        if not _safe_query_text(keyword, maximum=80) or (
            city and not _safe_query_text(city, maximum=50)
        ):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        now = datetime.now(UTC)
        payload = await self._request_json(
            "/v3/place/text",
            {
                "keywords": keyword,
                "city": city,
                "citylimit": "true" if city else "false",
                "offset": str(limit),
                "page": "1",
                "extensions": "base",
                "output": "JSON",
            },
        )
        records = payload.get("pois", [])
        if not isinstance(records, list):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        places: list[dict[str, str]] = []
        for record in records[:limit]:
            if not isinstance(record, dict):
                continue
            place_id = _text(record.get("id"))
            name = _text(record.get("name"))
            location = _coordinate(record.get("location"))
            if not place_id or not name or not location:
                continue
            places.append(
                {
                    "id": place_id,
                    "name": name,
                    "type": _text(record.get("type")),
                    "typecode": _text(record.get("typecode")),
                    "address": _text(record.get("address")),
                    "location": location,
                    "province": _text(record.get("pname")),
                    "city": _text(record.get("cityname")),
                    "district": _text(record.get("adname")),
                    "adcode": _text(record.get("adcode")),
                }
            )
        observation = self._observation(
            capability=query.capability,
            now=now,
            ttl_seconds=query.ttl_seconds,
            payload={"keyword": keyword, "city": city, "places": places},
            endpoint="/v3/place/text",
            sensitivity=DataSensitivity.PRECISE_LOCATION,
            confidence=0.85,
        )
        return WorldObservationBatch(
            source_id=self.SOURCE_ID,
            capability=query.capability,
            fetched_at=now,
            observations=(observation,),
        )

    async def _fetch_route(self, query: WorldQuery) -> WorldObservationBatch:
        if not query.consent_granted:
            raise WorldSourceError(WorldSourceErrorCode.CONSENT_REQUIRED)
        mode = query.parameters.get("mode", "").strip().lower()
        origin = _coordinate(query.parameters.get("origin"))
        destination = _coordinate(query.parameters.get("destination"))
        city = query.parameters.get("city", "").strip()
        destination_city = query.parameters.get("destination_city", "").strip()
        if mode not in {"driving", "transit", "walking"} or not origin or not destination:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        if (city and not _safe_query_text(city, maximum=50)) or (
            destination_city and not _safe_query_text(destination_city, maximum=50)
        ):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        if mode == "transit" and not city:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)

        endpoint = {
            "driving": "/v3/direction/driving",
            "transit": "/v3/direction/transit/integrated",
            "walking": "/v3/direction/walking",
        }[mode]
        parameters = {
            "origin": origin,
            "destination": destination,
            "output": "JSON",
            "extensions": "base",
        }
        if mode == "driving":
            parameters["strategy"] = "0"
        elif mode == "transit":
            parameters.update(
                {
                    "city": city,
                    "cityd": destination_city or city,
                    "strategy": "0",
                    "nightflag": "0",
                }
            )

        now = datetime.now(UTC)
        payload = await self._request_json(endpoint, parameters)
        route = payload.get("route")
        if not isinstance(route, dict):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        routes = _normalized_routes(route, mode=mode)
        if not routes:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        observation = self._observation(
            capability=query.capability,
            now=now,
            ttl_seconds=query.ttl_seconds,
            payload={"mode": mode, "routes": routes},
            endpoint=endpoint,
            sensitivity=DataSensitivity.PRECISE_LOCATION,
            confidence=0.75,
        )
        return WorldObservationBatch(
            source_id=self.SOURCE_ID,
            capability=query.capability,
            fetched_at=now,
            observations=(observation,),
        )

    async def _request_json(self, endpoint: str, parameters: dict[str, str]) -> dict[str, Any]:
        params = {**parameters, "key": self._api_key}
        try:
            response = (
                await self._client.get(
                    self._base_url + endpoint,
                    params=params,
                    timeout=self._timeout_seconds,
                )
                if self._client is not None
                else await self._default_get(endpoint, params)
            )
        except WorldSourceError:
            raise
        except TimeoutError as exc:
            raise WorldSourceError(WorldSourceErrorCode.TIMEOUT) from exc
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

        if len(response.content) > self._max_response_bytes:
            raise WorldSourceError(WorldSourceErrorCode.RESPONSE_TOO_LARGE)
        if response.status_code in {401, 403}:
            raise WorldSourceError(WorldSourceErrorCode.AUTHENTICATION_FAILED)
        if response.status_code == 429:
            raise WorldSourceError(WorldSourceErrorCode.RATE_LIMITED)
        if response.status_code >= 500:
            raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE)
        if response.status_code != 200:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        try:
            payload = response.json()
        except Exception as exc:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE) from exc
        if not isinstance(payload, dict):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        if str(payload.get("status", "")) != "1" or str(payload.get("infocode", "")) != "10000":
            info = str(payload.get("info", "")).upper()
            code = (
                WorldSourceErrorCode.AUTHENTICATION_FAILED
                if "KEY" in info or "USER" in info
                else WorldSourceErrorCode.INVALID_RESPONSE
            )
            raise WorldSourceError(code)
        return payload

    async def _default_get(self, endpoint: str, params: dict[str, str]) -> HttpResponse:
        import httpx

        async with httpx.AsyncClient(follow_redirects=False) as client:
            return await client.get(
                self._base_url + endpoint,
                params=params,
                timeout=self._timeout_seconds,
            )

    def _observation(
        self,
        *,
        capability: WorldSourceCapability,
        now: datetime,
        ttl_seconds: int,
        payload: dict[str, Any],
        endpoint: str,
        sensitivity: DataSensitivity,
        confidence: float,
    ) -> WorldObservation:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        evidence = WorldEvidence(
            source_id=self.SOURCE_ID,
            source_uri=self._base_url + endpoint,
            retrieved_at=now,
            content_hash=digest,
            license_id="amap-web-service",
        )
        return WorldObservation(
            observation_id=f"{self.SOURCE_ID}:{capability.value}:{digest[:24]}",
            capability=capability,
            observed_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            confidence=confidence,
            payload=payload,
            evidence=(evidence,),
            sensitivity=sensitivity,
        )


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_query_text(value: str, *, maximum: int) -> bool:
    return bool(value) and len(value) <= maximum and not any(ord(character) < 32 for character in value)


def _bounded_integer(value: str, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST) from exc
    if not minimum <= parsed <= maximum:
        raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
    return parsed


def _coordinate(value: Any) -> str:
    raw = _text(value)
    parts = raw.split(",")
    if len(parts) != 2:
        return ""
    try:
        longitude = float(parts[0])
        latitude = float(parts[1])
    except ValueError:
        return ""
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        return ""
    return f"{longitude:.6f},{latitude:.6f}"


def _number_text(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = float(raw)
    except ValueError:
        return ""
    if parsed < 0:
        return ""
    return str(int(parsed)) if parsed.is_integer() else f"{parsed:.2f}".rstrip("0").rstrip(".")


def _normalized_routes(route: dict[str, Any], *, mode: str) -> list[dict[str, Any]]:
    collection_name = "transits" if mode == "transit" else "paths"
    records = route.get(collection_name)
    if not isinstance(records, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records[:3], start=1):
        if not isinstance(record, dict):
            continue
        distance = _number_text(record.get("distance"))
        duration = _number_text(record.get("duration"))
        if not distance or not duration:
            continue
        lines: list[str] = []
        if mode == "transit":
            segments = record.get("segments", [])
            if isinstance(segments, list):
                for segment in segments[:20]:
                    if not isinstance(segment, dict):
                        continue
                    bus = segment.get("bus")
                    buslines = bus.get("buslines", []) if isinstance(bus, dict) else []
                    if not isinstance(buslines, list):
                        continue
                    for busline in buslines[:3]:
                        if isinstance(busline, dict):
                            name = _text(busline.get("name"))
                            if name and name not in lines:
                                lines.append(name)
        normalized.append(
            {
                "option": str(index),
                "distance_m": distance,
                "duration_seconds": duration,
                "cost_yuan": _number_text(
                    record.get("cost") if mode == "transit" else record.get("tolls")
                ),
                "walking_distance_m": _number_text(record.get("walking_distance")),
                "traffic_lights": _number_text(record.get("traffic_lights")),
                "strategy": _text(record.get("strategy")),
                "transit_lines": lines[:8],
            }
        )
    return normalized


def _normalized_casts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "date": _text(item.get("date")),
                "week": _text(item.get("week")),
                "day_weather": _text(item.get("dayweather")),
                "night_weather": _text(item.get("nightweather")),
                "day_temperature_c": _text(item.get("daytemp")),
                "night_temperature_c": _text(item.get("nighttemp")),
                "day_wind_direction": _text(item.get("daywind")),
                "night_wind_direction": _text(item.get("nightwind")),
                "day_wind_power": _text(item.get("daypower")),
                "night_wind_power": _text(item.get("nightpower")),
            }
        )
    return normalized
