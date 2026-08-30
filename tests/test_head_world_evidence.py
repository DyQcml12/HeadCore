from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.head.world_evidence import cognitive_facts_from_world_result
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldSourceCapability,
)


def weather_result(*, confidence: float = 0.8, sensitivity: DataSensitivity = DataSensitivity.PUBLIC) -> WorldAcquisitionResult:
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    observation = WorldObservation(
        observation_id="amap:weather:440100",
        capability=WorldSourceCapability.WEATHER_CURRENT,
        observed_at=now,
        expires_at=now + timedelta(minutes=15),
        confidence=confidence,
        sensitivity=sensitivity,
        payload={"adcode": "440100", "weather": "cloudy", "temperature_c": "30", "humidity_percent": "65"},
        evidence=(WorldEvidence("amap", "https://restapi.amap.com/v3/weather/weatherInfo", now, "a" * 64),),
    )
    return WorldAcquisitionResult(
        batch=WorldObservationBatch("amap", WorldSourceCapability.WEATHER_CURRENT, now, (observation,)),
        cache_hit=False,
        shared_request=False,
        cache_key="safe-cache-key",
    )


def test_public_current_weather_becomes_bounded_cognitive_facts() -> None:
    facts = cognitive_facts_from_world_result(weather_result(), version=3)

    assert {fact.key for fact in facts} == {
        "weather.440100.condition",
        "weather.440100.temperature_c",
        "weather.440100.humidity_percent",
    }
    assert {fact.version for fact in facts} == {3}
    assert all(fact.fact_id.startswith("world-") for fact in facts)


def test_low_confidence_or_nonpublic_observation_is_not_auto_persistable() -> None:
    assert cognitive_facts_from_world_result(weather_result(confidence=0.79)) == ()
    assert cognitive_facts_from_world_result(weather_result(sensitivity=DataSensitivity.COARSE_LOCATION)) == ()


def _list_result(
    capability: WorldSourceCapability,
    payload: dict,
) -> WorldAcquisitionResult:
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    observation = WorldObservation(
        observation_id=f"amap:{capability.value}:demo",
        capability=capability,
        observed_at=now,
        expires_at=now + timedelta(hours=3),
        confidence=0.8,
        sensitivity=DataSensitivity.PUBLIC,
        payload=payload,
        evidence=(WorldEvidence("amap", "https://restapi.amap.com/x", now, "c" * 64),),
    )
    return WorldAcquisitionResult(
        batch=WorldObservationBatch("amap", capability, now, (observation,)),
        cache_hit=False,
        shared_request=False,
        cache_key="safe-cache-key",
    )


def test_forecast_casts_become_per_day_facts() -> None:
    facts = cognitive_facts_from_world_result(
        _list_result(
            WorldSourceCapability.WEATHER_FORECAST,
            {
                "adcode": "440100",
                "casts": [
                    {"date": "2026-07-23", "day_weather": "雨", "night_weather": "多云",
                     "day_temperature_c": "30", "night_temperature_c": "24"},
                    {"date": "2026-07-24", "day_weather": "晴", "night_weather": "晴",
                     "day_temperature_c": "32", "night_temperature_c": "25"},
                ],
            },
        )
    )

    assert {fact.key for fact in facts} == {
        "weather.440100.2026-07-23.day_weather",
        "weather.440100.2026-07-23.night_weather",
        "weather.440100.2026-07-23.day_temperature_c",
        "weather.440100.2026-07-23.night_temperature_c",
        "weather.440100.2026-07-24.day_weather",
        "weather.440100.2026-07-24.night_weather",
        "weather.440100.2026-07-24.day_temperature_c",
        "weather.440100.2026-07-24.night_temperature_c",
    }


def test_policy_items_become_facts() -> None:
    facts = cognitive_facts_from_world_result(
        _list_result(
            WorldSourceCapability.POLICY,
            {
                "topic": "政策",
                "items": [
                    {"title": "某政策文件", "published_at": "2026-07-01", "url": "https://www.gov.cn/x"},
                ],
            },
        )
    )

    assert len(facts) == 3
    suffixes = {fact.key.rsplit(".", 1)[-1] for fact in facts}
    assert suffixes == {"title", "published_at", "url"}
    assert all(fact.key.startswith("policy.") for fact in facts)
