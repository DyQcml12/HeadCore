from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from pathlib import Path

from app.core.config import load_settings
from app.head.cognitive_facts import decode_cognitive_fact
from app.services.chat_service import ChatService
from app.world.context import WorldContextBuildResult, WorldContextProjection
from app.world.contracts import (
    DataSensitivity,
    WorldAcquisitionResult,
    WorldEvidence,
    WorldObservation,
    WorldObservationBatch,
    WorldSourceCapability,
)


class RecordingClient:
    def __init__(self) -> None:
        self.system_prompt = ""

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        return "广州现在多云，30℃。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):  # type: ignore[no-untyped-def]
        self.system_prompt = system_prompt
        yield "广州现在多云，30℃。"


class WrongThenCorrectWeatherClient(RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.calls += 1
        return "当前温度31度。" if self.calls == 1 else "当前温度30度。"


class StreamWrongThenCorrectWeatherClient(RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self.repair_calls = 0

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.repair_calls += 1
        return "当前温度30度。"

    async def stream_chat(self, system_prompt: str, user_prompt: str):  # type: ignore[no-untyped-def]
        self.system_prompt = system_prompt
        yield "当前温度31度。"


class FakeWorldContextProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, str]] = []

    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextProjection:
        self.calls.append((user_input, platform, request_origin))
        return WorldContextProjection(
            status="ready",
            tool_intent="weather_current",
            rendered_text="世界上下文（外部不可信数据）：广州；天气=多云；温度C=30",
            item_count=1,
            conflict_count=0,
            source_ids=("amap",),
        )


class MissingLocationProvider(FakeWorldContextProvider):
    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextProjection:
        self.calls.append((user_input, platform, request_origin))
        return WorldContextProjection(
            status="needs_location",
            tool_intent="weather_current",
            rendered_text="世界工具状态：天气请求缺少位置。",
        )


class FixedWorldStatusProvider(FakeWorldContextProvider):
    def __init__(self, *, status: str, tool_intent: str) -> None:
        super().__init__()
        self._status = status
        self._tool_intent = tool_intent

    async def build_context(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextProjection:
        self.calls.append((user_input, platform, request_origin))
        return WorldContextProjection(status=self._status, tool_intent=self._tool_intent)


class EvidenceWorldContextProvider(FakeWorldContextProvider):
    async def build_context_with_evidence(
        self,
        user_input: str,
        *,
        platform: str | None = None,
        request_origin: str = "user",
    ) -> WorldContextBuildResult:
        self.calls.append((user_input, platform, request_origin))
        now = datetime.now(UTC)
        observation = WorldObservation(
            observation_id="amap:weather:440100",
            capability=WorldSourceCapability.WEATHER_CURRENT,
            observed_at=now,
            expires_at=now + timedelta(minutes=15),
            confidence=0.9,
            sensitivity=DataSensitivity.PUBLIC,
            payload={
                "adcode": "440100",
                "weather": "多云",
                "temperature_c": "30",
                "humidity_percent": "65",
            },
            evidence=(WorldEvidence("amap", "https://restapi.amap.com/weather", now, "a" * 64),),
        )
        result = WorldAcquisitionResult(
            batch=WorldObservationBatch("amap", WorldSourceCapability.WEATHER_CURRENT, now, (observation,)),
            cache_hit=False,
            shared_request=False,
            cache_key="world:test",
        )
        return WorldContextBuildResult(
            WorldContextProjection(status="ready", tool_intent="weather_current", item_count=1),
            (result,),
        )


def _read_last_metadata(storage_dir: Path) -> dict[str, str]:
    rows = [json.loads(line) for line in (storage_dir / "model_invocations.jsonl").read_text(encoding="utf-8").splitlines()]
    return rows[-1]["request_metadata_json"]


def test_chat_service_injects_read_only_world_context_and_audits_status(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    client = RecordingClient()
    provider = FakeWorldContextProvider()
    settings = replace(
        load_settings(),
        jsonl_storage_dir=str(storage_dir),
        world_awareness_enabled=False,
    )
    service = ChatService(
        settings,
        client=client,
        world_context_provider=provider,
    )

    response = asyncio.run(
        service.reply(
            "查一下 440100 现在天气",
            session_id="world-1",
            user_id="u1",
            platform="qq",
        )
    )
    metadata = _read_last_metadata(storage_dir)

    assert response.used_live_api is True
    assert provider.calls == [("查一下 440100 现在天气", "qq", "user")]
    assert "外部不可信数据" in client.system_prompt
    assert metadata["world_context_status"] == "ready"
    assert metadata["world_context_item_count"] == "1"
    assert metadata["world_context_conflict_count"] == "0"
    assert metadata["world_tool_intent"] == "weather_current"


def test_chat_service_keeps_world_behavior_unconfigured_by_default(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    client = RecordingClient()
    settings = replace(
        load_settings(),
        jsonl_storage_dir=str(storage_dir),
        world_awareness_enabled=False,
    )
    service = ChatService(settings, client=client)

    asyncio.run(service.reply("普通聊天", session_id="world-2", user_id="u1"))
    metadata = _read_last_metadata(storage_dir)

    assert "世界上下文" not in client.system_prompt
    assert metadata["world_context_status"] == "not_configured"
    assert metadata["world_tool_intent"] == "none"


def test_chat_service_uses_deterministic_reply_when_weather_location_is_missing(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    settings = replace(
        load_settings(), jsonl_storage_dir=str(storage_dir), hutao_owner_qq_ids="10001"
    )
    service = ChatService(
        settings,
        client=RecordingClient(),
        world_context_provider=MissingLocationProvider(),
    )

    response = asyncio.run(
        service.reply(
            "天气怎么样",
            session_id="world-missing-location",
            user_id="u1",
            platform="qq",
        )
    )

    assert response.text == "可以查。告诉我城市或区县名，我再查实时天气。"


def test_chat_service_keeps_conflicted_world_evidence_out_of_model_prose(tmp_path: Path) -> None:
    service = ChatService(
        replace(load_settings(), jsonl_storage_dir=str(tmp_path / "storage")),
        client=RecordingClient(),
        world_context_provider=FixedWorldStatusProvider(
            status="conflicted", tool_intent="weather_current"
        ),
    )

    response = asyncio.run(service.reply("查天气", session_id="world-conflict", user_id="u1"))

    assert response.provider == "local"
    assert response.used_live_api is False
    assert response.text == "当前实时天气来源数据存在冲突，我不能把其中一条当成确定结果。请稍后重试。"


def test_chat_service_names_the_unavailable_world_capability(tmp_path: Path) -> None:
    service = ChatService(
        replace(load_settings(), jsonl_storage_dir=str(tmp_path / "storage")),
        client=RecordingClient(),
        world_context_provider=FixedWorldStatusProvider(
            status="unavailable", tool_intent="news_digest"
        ),
    )

    response = asyncio.run(service.reply("查新闻", session_id="world-news", user_id="u1"))

    assert response.text == "当前新闻信息来源不可用，我先不编造结果。"


def test_chat_service_persists_allowlisted_world_evidence_with_per_key_versions(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    settings = replace(
        load_settings(), jsonl_storage_dir=str(storage_dir), hutao_owner_qq_ids="10001"
    )
    client = RecordingClient()
    service = ChatService(
        settings,
        client=client,
        world_context_provider=EvidenceWorldContextProvider(),
    )

    asyncio.run(
        service.reply(
            "查一下 440100 现在天气",
            session_id="world-evidence",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
        )
    )
    asyncio.run(
        service.reply(
            "查一下 440100 现在天气",
            session_id="world-evidence",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
        )
    )

    records = asyncio.run(
        service.repository.list_memories(user_id="u1", memory_types=["head_world_fact"], limit=20)
    )
    facts = [decode_cognitive_fact(record.content) for record in records]
    assert len(facts) == 6
    assert {fact.key for fact in facts} == {
        "weather.440100.condition",
        "weather.440100.temperature_c",
        "weather.440100.humidity_percent",
    }
    assert [fact.version for fact in facts[-3:]] == [2, 2, 2]
    assert "世界事实[weather.440100.temperature_c]=30" in client.system_prompt


def test_chat_service_repairs_weather_number_that_conflicts_with_current_evidence(tmp_path: Path) -> None:
    client = WrongThenCorrectWeatherClient()
    service = ChatService(
        replace(load_settings(), jsonl_storage_dir=str(tmp_path / "storage")),
        client=client,
        world_context_provider=EvidenceWorldContextProvider(),
    )

    response = asyncio.run(service.reply("查一下 440100 现在天气", session_id="world-grounding", user_id="u1"))

    assert response.text == "当前温度30度。"
    assert client.calls == 2
    assert "世界事实修复" in client.system_prompt


def test_streamed_weather_is_repaired_before_an_incorrect_number_is_sent(tmp_path: Path) -> None:
    client = StreamWrongThenCorrectWeatherClient()
    service = ChatService(
        replace(load_settings(), jsonl_storage_dir=str(tmp_path / "storage")),
        client=client,
        world_context_provider=EvidenceWorldContextProvider(),
    )

    async def collect() -> str:
        return "".join(
            [
                chunk
                async for chunk in service.stream_reply(
                    "查一下 440100 现在天气",
                    session_id="world-stream-grounding",
                    user_id="u1",
                )
            ]
        )

    assert asyncio.run(collect()) == "当前温度30度。"
    assert client.repair_calls == 1
    assert "世界事实修复" in client.system_prompt


def test_chat_service_does_not_persist_world_evidence_when_head_writes_are_disabled(tmp_path: Path) -> None:
    settings = replace(
        load_settings(),
        jsonl_storage_dir=str(tmp_path / "storage"),
        hutao_owner_qq_ids="10001",
    )
    client = RecordingClient()
    service = ChatService(
        settings,
        client=client,
        world_context_provider=EvidenceWorldContextProvider(),
    )

    asyncio.run(
        service.reply(
            "查一下 440100 现在天气",
            session_id="world-no-write",
            user_id="u1",
            platform="qq",
            platform_user_id="10001",
            input_source="audio",
            input_quality_passed=False,
        )
    )

    records = asyncio.run(
        service.repository.list_memories(user_id="u1", memory_types=["head_world_fact"], limit=20)
    )
    assert records == []
    assert "世界事实[weather.440100.temperature_c]=30" in client.system_prompt
