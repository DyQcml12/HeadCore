from __future__ import annotations

import datetime as dt

from app.head.contracts import (
    CognitiveFact,
    CognitiveFactKind,
    CognitiveFactSourceKind,
    CognitiveFactStatus,
)
from app.head.world_calibration import calibrate_facts_with_observations
from app.head.world_evidence import cognitive_facts_from_world_result
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldSourceCapability,
)


NOW = dt.datetime(2026, 7, 22, 12, tzinfo=dt.UTC)


def observation(
    capability: WorldSourceCapability,
    payload: dict[str, object],
    *,
    confidence: float = 0.9,
    sensitivity: DataSensitivity = DataSensitivity.PUBLIC,
    observation_id: str = "obs-1",
) -> WorldObservation:
    return WorldObservation(
        observation_id=observation_id,
        capability=capability,
        observed_at=NOW,
        expires_at=NOW + dt.timedelta(hours=6),
        confidence=confidence,
        payload=payload,
        evidence=(
            WorldEvidence(
                source_id="fake-source",
                source_uri="https://example.com/news",
                retrieved_at=NOW,
                content_hash="h" * 64,
            ),
        ),
        sensitivity=sensitivity,
    )


def result(capability: WorldSourceCapability, observations) -> WorldAcquisitionResult:
    return WorldAcquisitionResult(
        batch=WorldObservationBatch(
            source_id="fake-source",
            capability=capability,
            fetched_at=NOW,
            observations=observations,
        ),
        cache_hit=False,
        shared_request=False,
        cache_key="",
    )


def fact(
    fact_id: str,
    key: str,
    value: str,
    *,
    source_id: str = "fake-source",
    version: int = 1,
    status: CognitiveFactStatus = CognitiveFactStatus.ACTIVE,
) -> CognitiveFact:
    return CognitiveFact(
        fact_id=fact_id,
        key=key,
        value=value,
        source_id=source_id,
        observed_at=NOW.isoformat(),
        expires_at=(NOW + dt.timedelta(hours=1)).isoformat(),
        confidence=0.9,
        version=version,
        status=status,
        kind=CognitiveFactKind.OBSERVATION,
        source_kind=CognitiveFactSourceKind.WORLD_EVIDENCE,
        supporting_source_ids=(source_id,),
    )

def test_news_observation_becomes_allowlisted_facts():
    facts = cognitive_facts_from_world_result(
        result(
            WorldSourceCapability.NEWS,
            (
                observation(
                    WorldSourceCapability.NEWS,
                    {
                        "topic": "world",
                        "items": [
                            {
                                "title": "联合国发布新报告",
                                "published_at": "2026-07-22T10:00:00+00:00",
                                "source_name": "news.un.org",
                                "url": "https://news.un.org/x",
                                "body_text": "完整正文不应进入事实",
                            }
                        ],
                    },
                ),
            ),
        ),
    )

    assert facts
    assert all(item.key.startswith("news.") for item in facts)
    assert all(any(item.key.endswith(suffix) for suffix in (".title", ".published_at", ".url")) for item in facts)
    assert all("正文" not in item.value for item in facts)
    assert all(item.source_kind == CognitiveFactSourceKind.WORLD_EVIDENCE for item in facts)


def test_ingestion_keeps_the_three_gates():
    low = cognitive_facts_from_world_result(
        result(
            WorldSourceCapability.NEWS,
            (observation(WorldSourceCapability.NEWS, {"title": "低置信新闻"}, confidence=0.5),),
        ),
    )
    private = cognitive_facts_from_world_result(
        result(
            WorldSourceCapability.WEATHER_CURRENT,
            (
                observation(
                    WorldSourceCapability.WEATHER_CURRENT,
                    {"adcode": "440100", "weather": "晴"},
                    sensitivity=DataSensitivity.PRECISE_LOCATION,
                ),
            ),
        ),
    )

    assert low == ()
    assert private == ()


def test_route_observation_uses_location_key():
    facts = cognitive_facts_from_world_result(
        result(
            WorldSourceCapability.MAP_ROUTE,
            (
                observation(
                    WorldSourceCapability.MAP_ROUTE,
                    {
                        "origin_id": "440100",
                        "destination_id": "440300",
                        "mode": "driving",
                        "routes": [
                            {"option": "1", "duration_seconds": 3600, "distance_m": 120000},
                        ],
                    },
                ),
            ),
        ),
    )

    assert any(item.key == "route.440100.440300.1.duration_seconds" for item in facts)

def test_calibration_dedupes_and_supersedes_same_source():
    existing = (fact("f1", "weather.440100.temperature_c", "28"),)
    incoming = (fact("f2", "weather.440100.temperature_c", "30", version=2),)

    report = calibrate_facts_with_observations(existing, incoming)

    assert report.duplicate_count == 0
    assert [item.fact_id for item in report.superseded_facts] == ["f1"]
    assert report.superseded_facts[0].status == CognitiveFactStatus.SUPERSEDED
    assert [item.fact_id for item in report.written_facts] == ["f2"]


def test_calibration_skips_exact_duplicate():
    existing = (fact("f1", "weather.440100.temperature_c", "28"),)
    incoming = (fact("f2", "weather.440100.temperature_c", "28", version=2),)

    report = calibrate_facts_with_observations(existing, incoming)

    assert report.duplicate_count == 1
    assert report.written_facts == ()
    assert report.superseded_facts == ()


def test_calibration_marks_cross_source_conflict():
    existing = (fact("f1", "weather.440100.temperature_c", "28", source_id="amap"),)
    incoming = (fact("f2", "weather.440100.temperature_c", "22", source_id="qweather"),)

    report = calibrate_facts_with_observations(existing, incoming)

    assert report.conflict_keys == ("weather.440100.temperature_c",)
    assert report.superseded_facts == ()
    assert [item.fact_id for item in report.written_facts] == ["f2"]
