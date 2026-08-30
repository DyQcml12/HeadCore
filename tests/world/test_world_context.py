from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.world.brain import (
    WorldBrainCoordinator,
    WorldRequestOrigin,
    WorldToolAccessMode,
    WorldToolIntent,
    decide_world_tools,
    world_tool_access_mode,
)
from app.world.context import WorldContextAssembler
from app.world.contracts import (
    WorldAcquisitionResult,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldSourceCapability,
)


def _weather_result(*, temperature: str = "30", expires_delta: int = 900):
    now = datetime.now(UTC)
    observed_at = now if expires_delta > 0 else now - timedelta(hours=1)
    evidence = WorldEvidence(
        source_id="amap",
        source_uri="https://restapi.amap.com/v3/weather/weatherInfo",
        retrieved_at=now,
        content_hash="a" * 64,
    )
    observation = WorldObservation(
        observation_id="amap:weather:one",
        capability=WorldSourceCapability.WEATHER_CURRENT,
        observed_at=observed_at,
        expires_at=now + timedelta(seconds=expires_delta),
        confidence=0.8,
        payload={
            "province": "广东",
            "city": "广州",
            "adcode": "440100",
            "weather": "多云",
            "temperature_c": temperature,
            "humidity_percent": "65",
            "wind_direction": "南",
            "wind_power": "1-3",
            "report_time": "2026-07-17 14:00:00",
        },
        evidence=(evidence,),
    )
    return WorldAcquisitionResult(
        batch=WorldObservationBatch(
            source_id="amap",
            capability=WorldSourceCapability.WEATHER_CURRENT,
            fetched_at=now,
            observations=(observation,),
        ),
        cache_hit=False,
        shared_request=False,
        cache_key="world:test",
    )


def _result(capability: WorldSourceCapability, payload: dict[str, object], *, tag: str):
    now = datetime.now(UTC)
    observation = WorldObservation(
        observation_id=f"amap:{tag}:one",
        capability=capability,
        observed_at=now,
        expires_at=now + timedelta(minutes=15),
        confidence=0.8,
        payload=payload,
        evidence=(
            WorldEvidence(
                source_id="amap",
                source_uri=f"https://restapi.amap.com/v3/{tag}",
                retrieved_at=now,
                content_hash=tag[0] * 64,
            ),
        ),
    )
    return WorldAcquisitionResult(
        batch=WorldObservationBatch(
            source_id="amap",
            capability=capability,
            fetched_at=now,
            observations=(observation,),
        ),
        cache_hit=False,
        shared_request=False,
        cache_key=f"world:{tag}",
    )
def test_world_tool_decision_requires_explicit_request_and_respects_opt_out() -> None:
    assert decide_world_tools("我刚看了新闻，心情有点乱").intent == WorldToolIntent.NONE
    assert decide_world_tools("不要联网查新闻").reason_code == "user_opted_out"
    news = decide_world_tools("帮我看看今天的国际新闻")
    assert news.intent == WorldToolIntent.NEWS_DIGEST
    assert news.topic == "world"
    assert news.source_ids == ("gdelt-doc", "un-news-en-rss")


def test_weather_decision_never_guesses_location() -> None:
    missing = decide_world_tools("明天天气怎么样")
    assert missing.intent == WorldToolIntent.WEATHER_FORECAST
    assert missing.requires_location is True
    explicit = decide_world_tools("查一下 440100 明天天气")
    assert explicit.adcode == "440100"
    assert explicit.requires_location is False
    city = decide_world_tools("帮我查一下广州明天天气")
    assert city.location_keyword == "广州"
    assert city.requires_location is False
    recent_city = decide_world_tools("最近长沙天气怎么样")
    assert recent_city.location_keyword == "长沙"
    assert recent_city.requires_location is False
    told_city = decide_world_tools("告诉我长沙天气怎么样")
    assert told_city.location_keyword == "长沙"
    assert told_city.requires_location is False


def test_travel_decision_extracts_only_endpoints_modes_and_time_constraint() -> None:
    decision = decide_world_tools(
        "我明天从广州南站到珠江新城，坐地铁还是开车，60分钟内到"
    )

    assert decision.intent == WorldToolIntent.TRAVEL_COMPARE
    assert decision.origin_keyword == "广州南站"
    assert decision.destination_keyword == "珠江新城"
    assert decision.travel_modes == ("transit", "driving")
    assert decision.time_budget_minutes == 60
    assert decision.day_offset == 1
    assert decision.requires_location is False


def test_travel_decision_refuses_to_guess_missing_endpoints() -> None:
    decision = decide_world_tools("帮我看看明天怎么去客户那里")

    assert decision.intent == WorldToolIntent.TRAVEL_COMPARE
    assert decision.requires_location is True


def test_weather_context_marks_external_data_untrusted_and_drops_stale() -> None:
    assembler = WorldContextAssembler()
    ready = assembler.from_weather(_weather_result(), tool_intent="weather_current")
    stale = assembler.from_weather(
        _weather_result(expires_delta=-1),
        tool_intent="weather_current",
    )

    assert ready.status == "ready"
    assert "外部不可信数据" in ready.rendered_text
    assert "广州" in ready.rendered_text
    assert "key=" not in ready.rendered_text
    assert stale.status == "stale"
    assert "不要把旧数据说成当前天气" in stale.rendered_text


def test_weather_context_marks_cross_source_conflicts() -> None:
    first = _weather_result().batch.observations[0]
    second_evidence = replace(
        first.evidence[0],
        source_id="weather-backup",
        source_uri="https://weather.example/current",
        content_hash="b" * 64,
    )
    second = replace(
        first,
        observation_id="backup:weather:two",
        payload={**first.payload, "weather": "晴", "temperature_c": "38"},
        evidence=(second_evidence,),
    )
    result = WorldAcquisitionResult(
        batch=WorldObservationBatch(
            source_id="weather-fusion",
            capability=WorldSourceCapability.WEATHER_CURRENT,
            fetched_at=datetime.now(UTC),
            observations=(first, second),
        ),
        cache_hit=False,
        shared_request=False,
        cache_key="world:weather-fusion",
    )

    projection = WorldContextAssembler().from_weather(
        result,
        tool_intent="weather_current",
    )

    assert projection.status == "conflicted"
    assert projection.conflict_count == 2
    assert {conflict.field for conflict in projection.conflicts} == {
        "temperature_c",
        "weather",
    }
    assert "必须明确说明" in projection.rendered_text


def test_district_resolution_requires_confirmation_for_same_name_candidates() -> None:
    now = datetime.now(UTC)
    evidence = WorldEvidence(
        source_id="amap",
        source_uri="https://restapi.amap.com/v3/config/district",
        retrieved_at=now,
        content_hash="d" * 64,
    )
    observation = WorldObservation(
        observation_id="amap:district:ambiguous",
        capability=WorldSourceCapability.MAP_PLACE,
        observed_at=now,
        expires_at=now + timedelta(days=30),
        confidence=0.9,
        payload={
            "keyword": "朝阳区",
            "districts": [
                {"name": "朝阳区", "adcode": "110105", "level": "district"},
                {"name": "朝阳区", "adcode": "220104", "level": "district"},
            ],
        },
        evidence=(evidence,),
    )
    result = WorldAcquisitionResult(
        batch=WorldObservationBatch(
            source_id="amap",
            capability=WorldSourceCapability.MAP_PLACE,
            fetched_at=now,
            observations=(observation,),
        ),
        cache_hit=False,
        shared_request=False,
        cache_key="world:district:ambiguous",
    )
    assembler = WorldContextAssembler()

    resolution = assembler.resolve_district(result, keyword="朝阳区")
    projection = assembler.district_confirmation(
        resolution,
        tool_intent="weather_current",
    )

    assert resolution.status == "ambiguous"
    assert projection.status == "needs_location_confirmation"
    assert "110105" in projection.rendered_text
    assert "220104" in projection.rendered_text

    city_observation = replace(
        observation,
        payload={
            "keyword": "长沙",
            "districts": [
                {"name": "长沙市", "adcode": "430100", "level": "city"},
                {"name": "长沙县", "adcode": "430121", "level": "district"},
            ],
        },
    )
    city_result = replace(
        result,
        batch=replace(result.batch, observations=(city_observation,)),
    )

    city_resolution = assembler.resolve_district(city_result, keyword="长沙")

    assert city_resolution.status == "resolved"
    assert city_resolution.adcode == "430100"


class FakeRuntimeStatus:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled


class FakeRuntime:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.weather_calls: list[str] = []
        self.district_calls: list[str] = []

    def status(self) -> FakeRuntimeStatus:
        return FakeRuntimeStatus(self.enabled)

    async def current_weather(self, adcode: str):  # type: ignore[no-untyped-def]
        self.weather_calls.append(adcode)
        return _weather_result()

    async def weather_forecast(self, adcode: str):  # type: ignore[no-untyped-def]
        self.weather_calls.append(adcode)
        return _weather_result()

    async def resolve_district(self, keyword: str):  # type: ignore[no-untyped-def]
        self.district_calls.append(keyword)
        now = datetime.now(UTC)
        evidence = WorldEvidence(
            source_id="amap",
            source_uri="https://restapi.amap.com/v3/config/district",
            retrieved_at=now,
            content_hash="c" * 64,
        )
        observation = WorldObservation(
            observation_id="amap:district:one",
            capability=WorldSourceCapability.MAP_PLACE,
            observed_at=now,
            expires_at=now + timedelta(days=30),
            confidence=0.9,
            payload={
                "keyword": keyword,
                "districts": [
                    {"name": "广州市", "adcode": "440100", "level": "city"}
                ],
            },
            evidence=(evidence,),
        )
        return WorldAcquisitionResult(
            batch=WorldObservationBatch(
                source_id="amap",
                capability=WorldSourceCapability.MAP_PLACE,
                fetched_at=now,
                observations=(observation,),
            ),
            cache_hit=False,
            shared_request=False,
            cache_key="world:district",
        )


def test_brain_coordinator_calls_tools_only_for_explicit_ready_requests() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        coordinator = WorldBrainCoordinator(runtime)

        normal = await coordinator.build_context("今天有点累")
        missing = await coordinator.build_context("明天天气怎么样")
        ready = await coordinator.build_context("查一下 440100 现在天气")
        city = await coordinator.build_context("帮我查一下广州明天天气")

        assert normal.status == "not_requested"
        assert missing.status == "needs_location"
        assert ready.status == "ready"
        assert city.status == "ready"
        assert runtime.district_calls == ["广州"]
        assert runtime.weather_calls[0] == "440100"
        assert runtime.weather_calls[1] == "440100"

    asyncio.run(scenario())


def test_brain_coordinator_exposes_ready_weather_as_persistable_evidence() -> None:
    async def scenario() -> None:
        coordinator = WorldBrainCoordinator(FakeRuntime())

        current = await coordinator.build_context_with_evidence("查一下 440100 现在天气")
        forecast = await coordinator.build_context_with_evidence("查一下 440100 明天天气")
        missing = await coordinator.build_context_with_evidence("明天天气怎么样")

        assert current.projection.status == "ready"
        assert len(current.persistable_results) == 1
        assert len(forecast.persistable_results) == 1
        assert missing.persistable_results == ()

    asyncio.run(scenario())


def test_platform_world_policy_blocks_proactive_qq_and_weixin_calls() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime()
        coordinator = WorldBrainCoordinator(runtime)

        qq = await coordinator.build_context(
            "查一下 440100 现在天气",
            platform="qq",
            request_origin=WorldRequestOrigin.SYSTEM,
        )
        weixin = await coordinator.build_context(
            "查一下 440100 现在天气",
            platform="weixin",
            request_origin="system",
        )

        assert qq.status == "proactive_denied"
        assert weixin.status == "proactive_denied"
        assert runtime.weather_calls == []

    assert world_tool_access_mode("qq") == WorldToolAccessMode.REACTIVE_ONLY
    assert world_tool_access_mode("weixin") == WorldToolAccessMode.REACTIVE_ONLY
    assert world_tool_access_mode("desktop_pet") == WorldToolAccessMode.PROACTIVE_CAPABLE
    assert world_tool_access_mode("app") == WorldToolAccessMode.PROACTIVE_CAPABLE
    asyncio.run(scenario())


class FakeTravelRuntime:
    def __init__(self) -> None:
        self.place_calls: list[tuple[str, str, int]] = []
        self.route_calls: list[tuple[str, bool]] = []
        self.weather_calls: list[str] = []

    def status(self) -> FakeRuntimeStatus:
        return FakeRuntimeStatus(True)

    async def search_places(
        self,
        keyword: str,
        *,
        city: str = "",
        limit: int = 5,
    ):
        self.place_calls.append((keyword, city, limit))
        values = {
            "广州南站": {
                "id": "origin",
                "name": "广州南站",
                "address": "石壁街道",
                "location": "113.269100,22.988900",
                "city": "广州市",
                "district": "番禺区",
                "adcode": "440113",
            },
            "珠江新城": {
                "id": "destination",
                "name": "珠江新城",
                "address": "花城大道",
                "location": "113.321900,23.119700",
                "city": "广州市",
                "district": "天河区",
                "adcode": "440106",
            },
        }
        return _result(
            WorldSourceCapability.MAP_PLACE,
            {"keyword": keyword, "places": [values[keyword]]},
            tag="place/text",
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
    ):
        self.route_calls.append((mode, consent_granted))
        route = {
            "distance_m": "18500",
            "duration_seconds": "2700" if mode == "transit" else "3300",
            "cost_yuan": "6" if mode == "transit" else "10",
            "walking_distance_m": "650" if mode == "transit" else "",
            "traffic_lights": "" if mode == "transit" else "24",
            "transit_lines": ["地铁2号线"] if mode == "transit" else [],
        }
        return _result(
            WorldSourceCapability.MAP_ROUTE,
            {"mode": mode, "routes": [route]},
            tag=f"direction/{mode}",
        )

    async def weather_forecast(self, adcode: str):
        self.weather_calls.append(adcode)
        return _result(
            WorldSourceCapability.WEATHER_FORECAST,
            {
                "adcode": adcode,
                "casts": [
                    {"day_weather": "多云", "night_weather": "多云"},
                    {"day_weather": "大雨", "night_weather": "阵雨"},
                ],
            },
            tag="weather/weatherInfo",
        )


def test_brain_compares_travel_consequences_without_claiming_future_traffic() -> None:
    async def scenario() -> None:
        runtime = FakeTravelRuntime()
        projection = await WorldBrainCoordinator(runtime).build_context(
            "我明天从广州南站到珠江新城，坐地铁还是开车，60分钟内到"
        )

        assert projection.status == "ready"
        assert projection.tool_intent == "travel_compare"
        assert projection.item_count == 2
        assert "公共交通" in projection.rendered_text
        assert "驾车" in projection.rendered_text
        assert "大雨/阵雨" in projection.rendered_text
        assert "满足预算=是" in projection.rendered_text
        assert "满足预算=否" in projection.rendered_text
        assert "不是模型对未来交通的确定预测" in projection.rendered_text
        assert "113.269100" not in projection.rendered_text
        assert runtime.place_calls == [("广州南站", "", 5), ("珠江新城", "", 5)]
        assert runtime.route_calls == [("transit", True), ("driving", True)]
        assert runtime.weather_calls == ["440106"]

    asyncio.run(scenario())


def test_brain_coordinator_does_not_call_disabled_runtime() -> None:
    async def scenario() -> None:
        runtime = FakeRuntime(enabled=False)
        projection = await WorldBrainCoordinator(runtime).build_context(
            "查一下 440100 现在天气"
        )

        assert projection.status == "disabled"
        assert runtime.weather_calls == []

    asyncio.run(scenario())
