from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.world.adapters.amap import AmapWorldSourceAdapter
from app.world.contracts import (
    DataSensitivity,
    WorldQuery,
    WorldSourceCapability,
)
from app.world.errors import WorldSourceError, WorldSourceErrorCode


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8")

    def json(self) -> dict[str, Any]:
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


def build_adapter(client: FakeHttpClient, *, api_key: str = "test-key") -> AmapWorldSourceAdapter:
    return AmapWorldSourceAdapter(
        api_key=api_key,
        client=client,
        enabled=True,
        legal_approved=True,
    )


def test_ip_location_requires_explicit_consent() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(FakeResponse({"status": "1", "infocode": "10000"}))
        adapter = build_adapter(client)
        with pytest.raises(WorldSourceError) as captured:
            await adapter.fetch(
                WorldQuery(
                    source_id="amap",
                    capability=WorldSourceCapability.IP_LOCATION,
                    parameters={"ip": "114.247.50.2"},
                )
            )
        assert captured.value.code == WorldSourceErrorCode.CONSENT_REQUIRED
        assert client.requests == []

    asyncio.run(scenario())


def test_ip_location_returns_only_coarse_location() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                {
                    "status": "1",
                    "infocode": "10000",
                    "province": "广东省",
                    "city": "广州市",
                    "adcode": "440100",
                    "rectangle": "ignored",
                }
            )
        )
        adapter = build_adapter(client)
        batch = await adapter.fetch(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.IP_LOCATION,
                parameters={"ip": "114.247.50.2"},
                consent_granted=True,
                sensitivity=DataSensitivity.COARSE_LOCATION,
                ttl_seconds=3600,
            )
        )
        observation = batch.observations[0]

        assert observation.payload == {
            "province": "广东省",
            "city": "广州市",
            "adcode": "440100",
        }
        assert observation.sensitivity == DataSensitivity.COARSE_LOCATION
        assert "114.247.50.2" not in json.dumps(observation.payload)
        assert "key=" not in observation.evidence[0].source_uri
        assert client.requests[0][1]["key"] == "test-key"
        assert client.requests[0][1]["output"] == "JSON"

    asyncio.run(scenario())


def test_current_weather_is_normalized() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                {
                    "status": "1",
                    "infocode": "10000",
                    "lives": [
                        {
                            "province": "广东",
                            "city": "广州",
                            "adcode": "440100",
                            "weather": "多云",
                            "temperature": "31",
                            "winddirection": "南",
                            "windpower": "≤3",
                            "humidity": "65",
                            "reporttime": "2026-07-17 10:00:00",
                        }
                    ],
                }
            )
        )
        adapter = build_adapter(client)
        batch = await adapter.fetch(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.WEATHER_CURRENT,
                parameters={"adcode": "440100"},
                ttl_seconds=900,
            )
        )
        payload = batch.observations[0].payload

        assert payload["weather"] == "多云"
        assert payload["temperature_c"] == "31"
        assert payload["humidity_percent"] == "65"
        assert client.requests[0][1]["extensions"] == "base"
        assert client.requests[0][1]["output"] == "JSON"

    asyncio.run(scenario())


def test_missing_api_key_fails_without_network() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(FakeResponse({"status": "1", "infocode": "10000"}))
        adapter = build_adapter(client, api_key="")
        with pytest.raises(WorldSourceError) as captured:
            await adapter.fetch(
                WorldQuery(
                    source_id="amap",
                    capability=WorldSourceCapability.WEATHER_CURRENT,
                    parameters={"adcode": "440100"},
                )
            )
        assert captured.value.code == WorldSourceErrorCode.NOT_CONFIGURED
        assert client.requests == []

    asyncio.run(scenario())


def test_ip_location_rejects_ipv6_without_network() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(FakeResponse({"status": "1", "infocode": "10000"}))
        adapter = build_adapter(client)
        with pytest.raises(WorldSourceError) as captured:
            await adapter.fetch(
                WorldQuery(
                    source_id="amap",
                    capability=WorldSourceCapability.IP_LOCATION,
                    parameters={"ip": "2001:4860:4860::8888"},
                    consent_granted=True,
                )
            )
        assert captured.value.code == WorldSourceErrorCode.INVALID_REQUEST
        assert client.requests == []

    asyncio.run(scenario())


def test_forecast_weather_is_normalized() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                {
                    "status": "1",
                    "infocode": "10000",
                    "forecasts": [
                        {
                            "province": "广东",
                            "city": "广州",
                            "adcode": "440100",
                            "reporttime": "2026-07-17 11:00:00",
                            "casts": [
                                {
                                    "date": "2026-07-17",
                                    "week": "5",
                                    "dayweather": "多云",
                                    "nightweather": "阵雨",
                                    "daytemp": "33",
                                    "nighttemp": "26",
                                    "daywind": "南",
                                    "nightwind": "南",
                                    "daypower": "1-3",
                                    "nightpower": "1-3",
                                }
                            ],
                        }
                    ],
                }
            )
        )
        adapter = build_adapter(client)
        batch = await adapter.fetch(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.WEATHER_FORECAST,
                parameters={"adcode": "440100"},
            )
        )

        assert batch.observations[0].payload["casts"][0]["day_temperature_c"] == "33"
        assert client.requests[0][1]["extensions"] == "all"

    asyncio.run(scenario())


def test_success_status_with_wrong_infocode_is_rejected() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse({"status": "1", "info": "INVALID_USER_KEY", "infocode": "10001"})
        )
        adapter = build_adapter(client)
        with pytest.raises(WorldSourceError) as captured:
            await adapter.fetch(
                WorldQuery(
                    source_id="amap",
                    capability=WorldSourceCapability.WEATHER_CURRENT,
                    parameters={"adcode": "440100"},
                )
            )
        assert captured.value.code == WorldSourceErrorCode.AUTHENTICATION_FAILED

    asyncio.run(scenario())


def test_district_lookup_normalizes_public_adcode_candidates() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                {
                    "status": "1",
                    "infocode": "10000",
                    "districts": [
                        {
                            "name": "广州市",
                            "adcode": "440100",
                            "citycode": "020",
                            "level": "city",
                            "center": "ignored",
                            "polyline": "ignored",
                        }
                    ],
                }
            )
        )
        adapter = build_adapter(client)
        batch = await adapter.fetch(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.MAP_PLACE,
                parameters={"keyword": "广州"},
                ttl_seconds=2592000,
            )
        )

        assert batch.observations[0].payload == {
            "keyword": "广州",
            "districts": [
                {
                    "name": "广州市",
                    "adcode": "440100",
                    "citycode": "020",
                    "level": "city",
                }
            ],
        }
        assert client.requests[0][0].endswith("/v3/config/district")
        assert client.requests[0][1]["subdistrict"] == "0"
        assert client.requests[0][1]["extensions"] == "base"
        assert "center" not in json.dumps(batch.observations[0].payload)

    asyncio.run(scenario())


def test_place_search_keeps_only_bounded_route_fields() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                {
                    "status": "1",
                    "infocode": "10000",
                    "pois": [
                        {
                            "id": "B001",
                            "name": "广州南站",
                            "type": "交通设施服务;火车站",
                            "typecode": "150200",
                            "address": "石壁街道",
                            "location": "113.269100,22.988900",
                            "pname": "广东省",
                            "cityname": "广州市",
                            "adname": "番禺区",
                            "adcode": "440113",
                            "tel": "ignored",
                            "photos": [{"url": "ignored"}],
                        }
                    ],
                }
            )
        )
        batch = await build_adapter(client).fetch(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.MAP_PLACE,
                parameters={
                    "operation": "place",
                    "keyword": "广州南站",
                    "city": "广州",
                    "limit": "5",
                },
            )
        )

        place = batch.observations[0].payload["places"][0]
        assert place["location"] == "113.269100,22.988900"
        assert place["city"] == "广州市"
        assert set(place) == {
            "id",
            "name",
            "type",
            "typecode",
            "address",
            "location",
            "province",
            "city",
            "district",
            "adcode",
        }
        assert batch.observations[0].sensitivity == DataSensitivity.PRECISE_LOCATION
        assert client.requests[0][0].endswith("/v3/place/text")
        assert client.requests[0][1]["citylimit"] == "true"

    asyncio.run(scenario())


def test_precise_route_requires_explicit_consent_without_network() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(FakeResponse({"status": "1", "infocode": "10000"}))
        with pytest.raises(WorldSourceError) as captured:
            await build_adapter(client).fetch(
                WorldQuery(
                    source_id="amap",
                    capability=WorldSourceCapability.MAP_ROUTE,
                    parameters={
                        "mode": "driving",
                        "origin": "113.269100,22.988900",
                        "destination": "113.321900,23.119700",
                    },
                )
            )
        assert captured.value.code == WorldSourceErrorCode.CONSENT_REQUIRED
        assert client.requests == []

    asyncio.run(scenario())


def test_transit_route_is_normalized_without_geometry() -> None:
    async def scenario() -> None:
        client = FakeHttpClient(
            FakeResponse(
                {
                    "status": "1",
                    "infocode": "10000",
                    "route": {
                        "origin": "ignored",
                        "destination": "ignored",
                        "transits": [
                            {
                                "cost": "6",
                                "duration": "2700",
                                "distance": "18500",
                                "walking_distance": "650",
                                "segments": [
                                    {
                                        "bus": {
                                            "buslines": [
                                                {"name": "地铁2号线(广州南站--嘉禾望岗)"}
                                            ]
                                        },
                                        "walking": {"steps": [{"polyline": "ignored"}]},
                                    }
                                ],
                            }
                        ],
                    },
                }
            )
        )
        batch = await build_adapter(client).fetch(
            WorldQuery(
                source_id="amap",
                capability=WorldSourceCapability.MAP_ROUTE,
                parameters={
                    "mode": "transit",
                    "origin": "113.269100,22.988900",
                    "destination": "113.321900,23.119700",
                    "city": "广州市",
                    "destination_city": "广州市",
                },
                consent_granted=True,
            )
        )

        route = batch.observations[0].payload["routes"][0]
        assert route["duration_seconds"] == "2700"
        assert route["walking_distance_m"] == "650"
        assert route["transit_lines"] == ["地铁2号线(广州南站--嘉禾望岗)"]
        assert "polyline" not in json.dumps(batch.observations[0].payload)
        assert client.requests[0][0].endswith("/v3/direction/transit/integrated")
        assert client.requests[0][1]["cityd"] == "广州市"

    asyncio.run(scenario())


def test_base_url_must_be_https_and_allowlisted() -> None:
    client = FakeHttpClient(FakeResponse({"status": "1"}))
    with pytest.raises(ValueError, match="https"):
        AmapWorldSourceAdapter(
            api_key="test-key",
            client=client,
            base_url="http://restapi.amap.com",
            enabled=True,
            legal_approved=True,
        )
    with pytest.raises(ValueError, match="allowlisted"):
        AmapWorldSourceAdapter(
            api_key="test-key",
            client=client,
            base_url="https://example.invalid",
            enabled=True,
            legal_approved=True,
        )
