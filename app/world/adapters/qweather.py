from __future__ import annotations

import hashlib
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


class QweatherWeatherAdapter:
    SOURCE_ID = "qweather"
    _CAPABILITIES = frozenset(
        {WorldSourceCapability.WEATHER_CURRENT, WorldSourceCapability.WEATHER_FORECAST}
    )

    def __init__(
        self,
        *,
        api_key: str,
        client: AsyncHttpClient | None = None,
        base_url: str = "https://devapi.qweather.com",
        allowed_hosts: tuple[str, ...] = ("devapi.qweather.com",),
        enabled: bool = False,
        legal_approved: bool = False,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        parsed = urlparse(base_url.rstrip("/"))
        hosts = tuple(host.strip().lower() for host in allowed_hosts if host.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("QWeather base_url must use https")
        if parsed.hostname.lower() not in hosts:
            raise ValueError("QWeather base_url host is not allowlisted")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("QWeather request limits must be positive")
        self.definition = WorldSourceDefinition(
            source_id=self.SOURCE_ID,
            kind=WorldSourceKind.API,
            capabilities=self._CAPABILITIES,
            enabled=enabled,
            legal_approved=legal_approved,
            terms_url="https://dev.qweather.com/docs/terms/tos/",
            allowed_hosts=hosts,
        )
        self._api_key = api_key.strip()
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    async def fetch(self, query: WorldQuery) -> WorldObservationBatch:
        if not self._api_key:
            raise WorldSourceError(WorldSourceErrorCode.NOT_CONFIGURED)
        location = query.parameters.get("location", "").strip()
        if not location or len(location) > 100 or any(ord(char) < 32 for char in location):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_REQUEST)
        location_record = await self._resolve_location(location)
        location_id = _text(location_record.get("id"))
        if not location_id:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        endpoint = "/v7/weather/now" if query.capability == WorldSourceCapability.WEATHER_CURRENT else "/v7/weather/3d"
        payload = await self._request_json(endpoint, {"location": location_id, "lang": "zh"})
        now = datetime.now(UTC)
        normalized = _normalize_weather(payload, query.capability, location_record)
        if not normalized:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        return WorldObservationBatch(
            source_id=self.SOURCE_ID,
            capability=query.capability,
            fetched_at=now,
            observations=(self._observation(query, now, normalized, endpoint),),
        )

    async def _resolve_location(self, location: str) -> dict[str, Any]:
        if location.isdigit() and len(location) >= 8:
            return {"id": location, "name": ""}
        payload = await self._request_json(
            "/geo/v2/city/lookup", {"location": location, "number": "10", "lang": "zh"}
        )
        records = payload.get("location")
        if not isinstance(records, list) or not records or not isinstance(records[0], dict):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        return records[0]

    async def _request_json(self, endpoint: str, parameters: dict[str, str]) -> dict[str, Any]:
        params = {**parameters, "key": self._api_key}
        try:
            response = await self._get(endpoint, params)
        except TimeoutError as exc:
            raise WorldSourceError(WorldSourceErrorCode.TIMEOUT) from exc
        except Exception as exc:
            raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE) from exc
        if len(response.content) > self._max_response_bytes:
            raise WorldSourceError(WorldSourceErrorCode.RESPONSE_TOO_LARGE)
        if response.status_code in {401, 403}:
            raise WorldSourceError(WorldSourceErrorCode.AUTHENTICATION_FAILED)
        if response.status_code == 429:
            raise WorldSourceError(WorldSourceErrorCode.RATE_LIMITED)
        if response.status_code != 200:
            raise WorldSourceError(WorldSourceErrorCode.UNAVAILABLE)
        try:
            payload = response.json()
        except Exception as exc:
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE) from exc
        if not isinstance(payload, dict):
            raise WorldSourceError(WorldSourceErrorCode.INVALID_RESPONSE)
        if str(payload.get("code", "")) != "200":
            code = WorldSourceErrorCode.AUTHENTICATION_FAILED if str(payload.get("code")) in {"401", "403"} else WorldSourceErrorCode.INVALID_RESPONSE
            raise WorldSourceError(code)
        return payload

    async def _get(self, endpoint: str, params: dict[str, str]) -> HttpResponse:
        if self._client is not None:
            return await self._client.get(self._base_url + endpoint, params=params, timeout=self._timeout_seconds)
        import httpx

        async with httpx.AsyncClient(follow_redirects=False) as client:
            return await client.get(self._base_url + endpoint, params=params, timeout=self._timeout_seconds)

    def _observation(self, query: WorldQuery, now: datetime, payload: dict[str, Any], endpoint: str) -> WorldObservation:
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return WorldObservation(
            observation_id=f"qweather:{query.capability.value}:{digest[:24]}",
            capability=query.capability,
            observed_at=now,
            expires_at=now + timedelta(seconds=query.ttl_seconds),
            confidence=0.85,
            payload=payload,
            evidence=(WorldEvidence("qweather", self._base_url + endpoint, now, digest, license_id="qweather-developers"),),
            sensitivity=DataSensitivity.PUBLIC,
        )


def _normalize_weather(payload: dict[str, Any], capability: WorldSourceCapability, location: dict[str, Any]) -> dict[str, Any]:
    common = {"city": _text(location.get("name")), "location_id": _text(location.get("id"))}
    if capability == WorldSourceCapability.WEATHER_CURRENT:
        current = payload.get("now")
        if not isinstance(current, dict):
            return {}
        return {**common, "weather": _text(current.get("text")), "temperature_c": _text(current.get("temp")), "wind_direction": _text(current.get("windDir")), "wind_power": _text(current.get("windScale")), "humidity_percent": _text(current.get("humidity")), "report_time": _text(current.get("obsTime"))}
    daily = payload.get("daily")
    if not isinstance(daily, list):
        return {}
    casts = [{"date": _text(item.get("fxDate")), "day_weather": _text(item.get("textDay")), "night_weather": _text(item.get("textNight")), "day_temperature_c": _text(item.get("tempMax")), "night_temperature_c": _text(item.get("tempMin")), "day_wind_direction": _text(item.get("windDirDay")), "night_wind_direction": _text(item.get("windDirNight")), "day_wind_power": _text(item.get("windScaleDay")), "night_wind_power": _text(item.get("windScaleNight"))} for item in daily[:3] if isinstance(item, dict)]
    return {**common, "casts": casts, "report_time": _text(payload.get("updateTime"))}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
