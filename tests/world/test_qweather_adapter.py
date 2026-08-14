from __future__ import annotations

import asyncio
import json

from app.world.adapters.qweather import QweatherWeatherAdapter
from app.world.contracts import WorldQuery, WorldSourceCapability


class FakeResponse:
    status_code = 200

    def __init__(self, body: dict[str, object]) -> None:
        self.content = json.dumps(body).encode("utf-8")
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, str]]] = []

    async def get(self, url: str, *, params: dict[str, str], timeout: float):
        self.requests.append((url, params))
        return self.responses.pop(0)


def test_qweather_resolves_city_then_normalizes_current_weather() -> None:
    async def scenario() -> None:
        client = FakeClient(
            [
                FakeResponse({"code": "200", "location": [{"id": "101280101", "name": "Guangzhou"}]}),
                FakeResponse({"code": "200", "now": {"text": "Cloudy", "temp": "31", "windDir": "North", "windScale": "3", "humidity": "72", "obsTime": "2026-07-23T10:00+08:00"}}),
            ]
        )
        adapter = QweatherWeatherAdapter(
            api_key="test-key", client=client, enabled=True, legal_approved=True
        )
        batch = await adapter.fetch(
            WorldQuery(
                source_id="qweather",
                capability=WorldSourceCapability.WEATHER_CURRENT,
                parameters={"location": "Guangzhou"},
            )
        )
        observation = batch.observations[0]
        assert observation.payload["temperature_c"] == "31"
        assert observation.payload["humidity_percent"] == "72"
        assert client.requests[0][0].endswith("/geo/v2/city/lookup")
        assert client.requests[1][0].endswith("/v7/weather/now")
        assert client.requests[1][1]["location"] == "101280101"
        assert "test-key" not in observation.evidence[0].source_uri

    asyncio.run(scenario())


def test_qweather_forecast_keeps_only_bounded_daily_fields() -> None:
    async def scenario() -> None:
        client = FakeClient(
            [
                FakeResponse({"code": "200", "daily": [{"fxDate": "2026-07-24", "textDay": "Sunny", "textNight": "Cloudy", "tempMax": "34", "tempMin": "26", "windDirDay": "East", "windDirNight": "East", "windScaleDay": "3", "windScaleNight": "3"}]}),
            ]
        )
        adapter = QweatherWeatherAdapter(api_key="test-key", client=client, enabled=True, legal_approved=True)
        batch = await adapter.fetch(WorldQuery(source_id="qweather", capability=WorldSourceCapability.WEATHER_FORECAST, parameters={"location": "101280101"}))
        cast = batch.observations[0].payload["casts"][0]
        assert cast["day_temperature_c"] == "34"
        assert set(cast) == {"date", "day_weather", "night_weather", "day_temperature_c", "night_temperature_c", "day_wind_direction", "night_wind_direction", "day_wind_power", "night_wind_power"}

    asyncio.run(scenario())
