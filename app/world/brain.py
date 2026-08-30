from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.world.context import (
    WorldContextAssembler,
    WorldContextBuildResult,
    WorldContextProjection,
)
from app.world.errors import WorldSourceError
from app.world.news_digest import NewsDigestResult


class WorldToolIntent(StrEnum):
    NONE = "none"
    WEATHER_CURRENT = "weather_current"
    WEATHER_FORECAST = "weather_forecast"
    NEWS_DIGEST = "news_digest"
    POLICY_UPDATES = "policy_updates"
    TRAVEL_COMPARE = "travel_compare"
    WEB_SEARCH = "web_search"


class WorldToolAccessMode(StrEnum):
    REACTIVE_ONLY = "reactive_only"
    PROACTIVE_CAPABLE = "proactive_capable"


class WorldRequestOrigin(StrEnum):
    USER = "user"
    SYSTEM = "system"
    MODEL_TOOL = "model_tool"


@dataclass(frozen=True)
class WorldToolDecision:
    intent: WorldToolIntent
    reason_code: str
    topic: str = ""
    adcode: str = ""
    location_keyword: str = ""
    source_ids: tuple[str, ...] = ()
    requires_location: bool = False
    origin_keyword: str = ""
    destination_keyword: str = ""
    city: str = ""
    travel_modes: tuple[str, ...] = ()
    time_budget_minutes: int | None = None
    day_offset: int = 0


class WorldRuntimeLike(Protocol):
    def status(self) -> object: ...

    async def current_weather(self, adcode: str): ...  # type: ignore[no-untyped-def]

    async def weather_forecast(self, adcode: str): ...  # type: ignore[no-untyped-def]

    async def resolve_district(self, keyword: str): ...  # type: ignore[no-untyped-def]

    async def search_places(
        self,
        keyword: str,
        *,
        city: str = "",
        limit: int = 5,
    ): ...  # type: ignore[no-untyped-def]

    async def route(
        self,
        origin: str,
        destination: str,
        *,
        mode: str,
        origin_city: str = "",
        destination_city: str = "",
        consent_granted: bool,
    ): ...  # type: ignore[no-untyped-def]

    async def policy_updates(
        self,
        source_id: str = "gov-cn-policy",
        *,
        topic: str = "",
        limit: int = 20,
    ): ...  # type: ignore[no-untyped-def]

    async def news_digest(
        self,
        *,
        topic: str,
        source_ids: tuple[str, ...],
        per_source_limit: int = 20,
        max_items: int = 30,
    ) -> NewsDigestResult: ...

    async def search(
        self,
        query: str,
        *,
        limit: int = 6,
    ): ...  # type: ignore[no-untyped-def]


_REQUEST_MARKERS = (
    "查",
    "看看",
    "想知道",
    "告诉我",
    "有什么",
    "最新",
    "今天",
    "最近",
    "怎么样",
    "多少度",
    "会下雨",
    "预报",
    "怎么去",
    "路线",
    "坐地铁",
    "坐公交",
    "开车",
    "驾车",
    "步行",
    "还是",
    "搜",
)
_OPT_OUT_MARKERS = ("不要查", "别查", "不要联网", "别联网", "不用查", "别调用")
_WEATHER_MARKERS = ("天气", "温度", "多少度", "下雨", "降雨", "穿衣")
_POLICY_MARKERS = ("政策", "国务院", "法规", "规划", "政府文件")
_NEWS_MARKERS = ("新闻", "资讯", "热点", "发生了什么")
_SEARCH_MARKERS = ("搜索", "搜一下", "网搜", "搜")
_FORECAST_MARKERS = ("明天", "后天", "未来", "预报")
_TRAVEL_MARKERS = ("怎么去", "路线", "地铁", "公交", "公共交通", "开车", "驾车", "自驾", "步行", "走路")


def decide_world_tools(user_input: str) -> WorldToolDecision:
    text = user_input.strip()[:500]
    if not text:
        return WorldToolDecision(WorldToolIntent.NONE, "empty_input")
    if any(marker in text for marker in _OPT_OUT_MARKERS):
        return WorldToolDecision(WorldToolIntent.NONE, "user_opted_out")
    explicit_request = any(marker in text for marker in _REQUEST_MARKERS)
    if not explicit_request:
        return WorldToolDecision(WorldToolIntent.NONE, "no_explicit_world_request")

    if any(marker in text for marker in _TRAVEL_MARKERS):
        origin, destination = _travel_endpoints(text)
        return WorldToolDecision(
            WorldToolIntent.TRAVEL_COMPARE,
            "explicit_travel_request",
            requires_location=not origin or not destination,
            origin_keyword=origin,
            destination_keyword=destination,
            city=_travel_city(text),
            travel_modes=_travel_modes(text),
            time_budget_minutes=_travel_time_budget(text),
            day_offset=2 if "后天" in text else 1 if "明天" in text else 0,
        )

    if any(marker in text for marker in _WEATHER_MARKERS):
        adcode_match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        location_keyword = "" if adcode_match else _weather_location_keyword(text)
        forecast = any(marker in text for marker in _FORECAST_MARKERS)
        return WorldToolDecision(
            WorldToolIntent.WEATHER_FORECAST if forecast else WorldToolIntent.WEATHER_CURRENT,
            "explicit_weather_request",
            adcode=adcode_match.group(1) if adcode_match else "",
            location_keyword=location_keyword,
            requires_location=adcode_match is None and not location_keyword,
        )
    if any(marker in text for marker in _POLICY_MARKERS):
        return WorldToolDecision(
            WorldToolIntent.POLICY_UPDATES,
            "explicit_policy_request",
            topic=_topic_for_text(text, policy=True),
            source_ids=("gov-cn-policy",),
        )
    if any(marker in text for marker in _NEWS_MARKERS):
        topic = _topic_for_text(text)
        sources = (
            ("gdelt-doc", "un-news-en-rss", "who-news-en-rss")
            if topic == "health"
            else ("gdelt-doc", "un-news-en-rss")
        )
        return WorldToolDecision(
            WorldToolIntent.NEWS_DIGEST,
            "explicit_news_request",
            topic=topic,
            source_ids=sources,
        )
    if any(marker in text for marker in _SEARCH_MARKERS):
        return WorldToolDecision(
            WorldToolIntent.WEB_SEARCH,
            "explicit_search_request",
            topic=_search_query(text),
        )
    return WorldToolDecision(WorldToolIntent.NONE, "unsupported_world_request")


def world_tool_access_mode(platform: str | None) -> WorldToolAccessMode:
    normalized = (platform or "").strip().lower().replace("-", "_")
    if normalized in {"web", "desktop", "desktop_pet", "app", "mobile_app"}:
        return WorldToolAccessMode.PROACTIVE_CAPABLE
    return WorldToolAccessMode.REACTIVE_ONLY


class WorldBrainCoordinator:
    def __init__(
        self,
        runtime: WorldRuntimeLike,
        *,
        assembler: WorldContextAssembler | None = None,
    ) -> None:
        self._runtime = runtime
        self._assembler = assembler or WorldContextAssembler()

    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: WorldRequestOrigin | str = WorldRequestOrigin.USER,
    ) -> WorldContextProjection:
        result = await self.build_context_with_evidence(
            user_input,
            platform=platform,
            request_origin=request_origin,
        )
        return result.projection

    async def build_context_with_evidence(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: WorldRequestOrigin | str = WorldRequestOrigin.USER,
    ) -> WorldContextBuildResult:
        origin = WorldRequestOrigin(request_origin)
        access_mode = world_tool_access_mode(platform)
        if origin == WorldRequestOrigin.SYSTEM and access_mode == WorldToolAccessMode.REACTIVE_ONLY:
            return WorldContextBuildResult(self._assembler.proactive_denied())
        decision = decide_world_tools(user_input)
        if decision.intent == WorldToolIntent.NONE:
            return WorldContextBuildResult(self._assembler.not_requested())
        if decision.requires_location:
            if decision.intent == WorldToolIntent.TRAVEL_COMPARE:
                return WorldContextBuildResult(
                    self._assembler.needs_travel_endpoints(decision.intent.value)
                )
            return WorldContextBuildResult(self._assembler.needs_location(decision.intent.value))
        if not bool(getattr(self._runtime.status(), "enabled", False)):
            return WorldContextBuildResult(self._assembler.disabled(decision.intent.value))
        try:
            weather_location = decision.adcode or decision.location_keyword
            if decision.intent in {
                WorldToolIntent.WEATHER_CURRENT,
                WorldToolIntent.WEATHER_FORECAST,
            } and decision.location_keyword:
                district_result = await self._runtime.resolve_district(
                    decision.location_keyword
                )
                resolution = self._assembler.resolve_district(
                    district_result,
                    keyword=decision.location_keyword,
                )
                if resolution.status != "resolved":
                    return WorldContextBuildResult(
                        self._assembler.district_confirmation(
                            resolution,
                            tool_intent=decision.intent.value,
                        )
                    )
                weather_location = resolution.candidates[0].adcode
            if decision.intent == WorldToolIntent.WEATHER_CURRENT:
                result = await self._runtime.current_weather(weather_location)
                projection = self._assembler.from_weather(result, tool_intent=decision.intent.value)
                evidence = (result,) if projection.status == "ready" else ()
                return WorldContextBuildResult(projection, evidence)
            if decision.intent == WorldToolIntent.WEATHER_FORECAST:
                result = await self._runtime.weather_forecast(weather_location)
                projection = self._assembler.from_weather(result, tool_intent=decision.intent.value)
                evidence = (result,) if projection.status == "ready" else ()
                return WorldContextBuildResult(projection, evidence)
            if decision.intent == WorldToolIntent.POLICY_UPDATES:
                result = await self._runtime.policy_updates(
                    decision.source_ids[0],
                    topic=decision.topic,
                    limit=8,
                )
                projection = self._assembler.from_policy(result, tool_intent=decision.intent.value)
                evidence = (result,) if projection.status == "ready" else ()
                return WorldContextBuildResult(projection, evidence)
            if decision.intent == WorldToolIntent.NEWS_DIGEST:
                result = await self._runtime.news_digest(
                    topic=decision.topic,
                    source_ids=decision.source_ids,
                    per_source_limit=10,
                    max_items=12,
                )
                return WorldContextBuildResult(
                    self._assembler.from_news_digest(result, tool_intent=decision.intent.value)
                )
            if decision.intent == WorldToolIntent.WEB_SEARCH:
                result = await self._runtime.search(decision.topic)
                projection = self._assembler.from_search(result, tool_intent=decision.intent.value)
                # Search results are realtime and cached in memory only; they are
                # never returned as persistable evidence, so they never reach the
                # fact store or the knowledge graph.
                return WorldContextBuildResult(projection)
            if decision.intent == WorldToolIntent.TRAVEL_COMPARE:
                origin_result, destination_result = await asyncio.gather(
                    self._runtime.search_places(
                        decision.origin_keyword,
                        city=decision.city,
                        limit=5,
                    ),
                    self._runtime.search_places(
                        decision.destination_keyword,
                        city=decision.city,
                        limit=5,
                    ),
                )
                origin_resolution = self._assembler.resolve_place(
                    origin_result,
                    keyword=decision.origin_keyword,
                )
                if origin_resolution.status != "resolved" or origin_resolution.candidate is None:
                    return WorldContextBuildResult(
                        self._assembler.place_confirmation(
                            origin_resolution,
                            endpoint_name="起点",
                            tool_intent=decision.intent.value,
                        )
                    )
                destination_resolution = self._assembler.resolve_place(
                    destination_result,
                    keyword=decision.destination_keyword,
                )
                if (
                    destination_resolution.status != "resolved"
                    or destination_resolution.candidate is None
                ):
                    return WorldContextBuildResult(
                        self._assembler.place_confirmation(
                            destination_resolution,
                            endpoint_name="终点",
                            tool_intent=decision.intent.value,
                        )
                    )
                origin = origin_resolution.candidate
                destination = destination_resolution.candidate
                route_values = await asyncio.gather(
                    *(
                        self._runtime.route(
                            origin.location,
                            destination.location,
                            mode=mode,
                            origin_city=origin.city or origin.adcode,
                            destination_city=destination.city or destination.adcode,
                            consent_granted=True,
                        )
                        for mode in decision.travel_modes
                    ),
                    return_exceptions=True,
                )
                route_results = tuple(
                    value for value in route_values if not isinstance(value, Exception)
                )
                weather_result = None
                if decision.day_offset > 0 and destination.adcode:
                    try:
                        weather_result = await self._runtime.weather_forecast(
                            destination.adcode
                        )
                    except (WorldSourceError, ValueError):
                        weather_result = None
                projection = self._assembler.from_travel_plan(
                    route_results,
                    origin=origin,
                    destination=destination,
                    expected_modes=decision.travel_modes,
                    time_budget_minutes=decision.time_budget_minutes,
                    day_offset=decision.day_offset,
                    weather_result=weather_result,
                    tool_intent=decision.intent.value,
                )
                evidence = route_results if weather_result is None else (*route_results, weather_result)
                return WorldContextBuildResult(projection, evidence)
        except (WorldSourceError, ValueError):
            return WorldContextBuildResult(self._assembler.unavailable(decision.intent.value))
        return WorldContextBuildResult(self._assembler.unavailable(decision.intent.value))


def _topic_for_text(text: str, *, policy: bool = False) -> str:
    mappings = (
        (("健康", "医疗", "卫生"), "health"),
        (("科技", "人工智能", "AI"), "technology"),
        (("财经", "金融", "经济", "股票"), "finance"),
        (("教育",), "education"),
        (("环境", "环保", "气候"), "environment"),
        (("中国", "国内"), "China"),
        (("国际", "全球", "世界"), "world"),
    )
    for markers, topic in mappings:
        if any(marker in text for marker in markers):
            return topic
    return "政策" if policy else "world"


def _search_query(text: str) -> str:
    cleaned = text
    for marker in (
        "帮我搜索一下",
        "帮我搜一下",
        "帮我搜索",
        "搜索一下",
        "搜索",
        "搜一下",
        "网搜",
        "搜",
    ):
        cleaned = cleaned.replace(marker, "")
    for char in ("，", ",", "。", "！", "!", "？", "?", " ", "请"):
        cleaned = cleaned.replace(char, "")
    return cleaned.strip()[:120]


def _weather_location_keyword(text: str) -> str:
    cleaned = text
    removable = (
        "帮我查一下",
        "帮我看看",
        "告诉我",
        "跟我说",
        "和我说",
        "请问",
        "查一下",
        "看一下",
        "看看",
        "今天",
        "现在",
        "最近",
        "近期",
        "目前",
        "明天",
        "后天",
        "未来",
        "的天气预报",
        "天气预报",
        "的天气",
        "天气",
        "的温度",
        "温度",
        "多少度",
        "怎么样",
        "会不会下雨",
        "会下雨吗",
        "下雨吗",
        "请",
        "？",
        "?",
        "。",
        "，",
        ",",
        " ",
    )
    for marker in removable:
        cleaned = cleaned.replace(marker, "")
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,12}", cleaned):
        return ""
    if any(marker in cleaned for marker in ("我", "去", "拜访", "客户", "想", "知道")):
        return ""
    return cleaned


def _travel_endpoints(text: str) -> tuple[str, str]:
    match = re.search(
        r"从(?P<origin>[^，。？！?,]{2,60}?)到(?P<destination>[^，。？！?,]{2,60}?)"
        r"(?=，|,|。|！|!|？|\?|坐|乘|开车|驾车|自驾|步行|走路|怎么|哪|$)",
        text,
    )
    if match is None:
        return "", ""
    return (
        _clean_place_keyword(match.group("origin")),
        _clean_place_keyword(match.group("destination")),
    )


def _clean_place_keyword(value: str) -> str:
    cleaned = value.strip(" ，,。！？?：:")
    if not 2 <= len(cleaned) <= 60:
        return ""
    if not re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·•()（）\-—_\s]+", cleaned):
        return ""
    return re.sub(r"\s+", " ", cleaned)


def _travel_city(text: str) -> str:
    match = re.search(r"(?:在|位于)([\u4e00-\u9fff]{2,12})(?=从)", text)
    return match.group(1) if match else ""


def _travel_modes(text: str) -> tuple[str, ...]:
    modes: list[str] = []
    if any(marker in text for marker in ("地铁", "公交", "公共交通", "乘车")):
        modes.append("transit")
    if any(marker in text for marker in ("开车", "驾车", "自驾")):
        modes.append("driving")
    if any(marker in text for marker in ("步行", "走路")):
        modes.append("walking")
    return tuple(modes or ("transit", "driving"))


def _travel_time_budget(text: str) -> int | None:
    minutes = re.search(r"(?<!\d)(\d{1,3})\s*(?:分钟|分)内", text)
    if minutes:
        value = int(minutes.group(1))
        return value if 1 <= value <= 720 else None
    hours = re.search(r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*小时内", text)
    if hours:
        value = round(float(hours.group(1)) * 60)
        return value if 1 <= value <= 720 else None
    clocks = re.search(
        r"(?<!\d)(\d{1,2})(?:点|时|:00)\s*(?:出发)?[^\d]{0,12}"
        r"(\d{1,2})(?:点|时|:00)\s*(?:前)?(?:到|到达|抵达)",
        text,
    )
    if clocks:
        departure, arrival = (int(value) for value in clocks.groups())
        budget = arrival * 60 - departure * 60
        return budget if 1 <= budget <= 720 else None
    return None
