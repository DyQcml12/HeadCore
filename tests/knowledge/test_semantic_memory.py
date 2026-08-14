from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx

from app.knowledge.models import MemoryRecord, MemoryScope, MemoryState
from app.knowledge.repository import InMemoryKnowledgeRepository
from app.knowledge.runtime import (
    LifecycleMemoryProjectionProvider,
    MemoryProjectionRequest,
)
from app.knowledge.semantic_memory import (
    InMemorySemanticMemoryIndex,
    OpenAICompatibleEmbeddingProvider,
    QdrantSemanticMemoryIndex,
    SemanticMemoryIndexUnavailableError,
    SemanticMemoryProjectionProvider,
)
from app.knowledge.service import KnowledgeLifecycleService


class MappingEmbeddingProvider:
    def __init__(self, vectors: dict[str, tuple[float, ...]]) -> None:
        self._vectors = vectors

    async def embed(self, text: str) -> tuple[float, ...]:
        return self._vectors[text]


class UnavailableSemanticMemoryIndex:
    async def search(self, **_: object) -> tuple[object, ...]:
        raise SemanticMemoryIndexUnavailableError("index_unavailable")


def _record(
    *,
    record_id: str,
    profile_id: str,
    key: str,
    value: str,
    state: MemoryState = MemoryState.ACTIVE,
    expires_at: datetime | None = None,
) -> MemoryRecord:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    return MemoryRecord(
        id=record_id,
        candidate_id=f"candidate-{record_id}",
        profile_id=profile_id,
        key=key,
        value=value,
        scope=MemoryScope.PROFILE_PRIVATE,
        source_type="user_statement",
        source_id=f"message-{record_id}",
        confidence=0.9,
        state=state,
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
    )


def _request(query: str) -> MemoryProjectionRequest:
    return MemoryProjectionRequest(
        profile_id="profile-a",
        persona_id="hutao_v1",
        relationship_type="normal_friend",
        is_admin=False,
        query=query,
    )


def test_semantic_projection_returns_only_relevant_active_same_profile_memory() -> None:
    repository = InMemoryKnowledgeRepository()
    active_relevant = _record(
        record_id="memory-travel",
        profile_id="profile-a",
        key="travel_plan",
        value="十月想去杭州看西湖。",
    )
    active_unrelated = _record(
        record_id="memory-food",
        profile_id="profile-a",
        key="food_preference",
        value="不吃香菜。",
    )
    revoked = _record(
        record_id="memory-revoked",
        profile_id="profile-a",
        key="old_plan",
        value="已经取消的南京行程。",
        state=MemoryState.REVOKED,
    )
    expired = _record(
        record_id="memory-expired",
        profile_id="profile-a",
        key="expired_plan",
        value="已经过期的苏州行程。",
        expires_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    other_profile = _record(
        record_id="memory-other-profile",
        profile_id="profile-b",
        key="travel_plan",
        value="这是另一个用户的杭州行程。",
    )
    for record in (active_relevant, active_unrelated, revoked, expired, other_profile):
        asyncio.run(repository.add_record(record))

    index = InMemorySemanticMemoryIndex()
    asyncio.run(index.upsert(record_id="memory-travel", profile_id="profile-a", vector=(1.0, 0.0)))
    asyncio.run(index.upsert(record_id="memory-food", profile_id="profile-a", vector=(0.0, 1.0)))
    asyncio.run(index.upsert(record_id="memory-revoked", profile_id="profile-a", vector=(0.99, 0.01)))
    asyncio.run(index.upsert(record_id="memory-expired", profile_id="profile-a", vector=(0.98, 0.02)))
    asyncio.run(index.upsert(record_id="memory-other-profile", profile_id="profile-b", vector=(1.0, 0.0)))

    provider = SemanticMemoryProjectionProvider(
        LifecycleMemoryProjectionProvider(KnowledgeLifecycleService(repository)),
        index=index,
        embedding_provider=MappingEmbeddingProvider({"杭州行程怎么安排？": (1.0, 0.0)}),
    )

    projection = asyncio.run(provider.get_projection(_request("杭州行程怎么安排？")))

    assert [(item.key, item.value) for item in projection] == [
        ("travel_plan", "十月想去杭州看西湖。")
    ]


def test_semantic_projection_falls_back_to_authoritative_memory_when_index_is_unavailable() -> None:
    repository = InMemoryKnowledgeRepository()
    record = _record(
        record_id="memory-preference",
        profile_id="profile-a",
        key="reply_preference",
        value="技术问题希望分步骤回答。",
    )
    asyncio.run(repository.add_record(record))
    provider = SemanticMemoryProjectionProvider(
        LifecycleMemoryProjectionProvider(KnowledgeLifecycleService(repository)),
        index=UnavailableSemanticMemoryIndex(),
        embedding_provider=MappingEmbeddingProvider({"怎么排查问题？": (0.5, 0.5)}),
    )

    projection = asyncio.run(provider.get_projection(_request("怎么排查问题？")))

    assert [(item.key, item.value) for item in projection] == [
        ("reply_preference", "技术问题希望分步骤回答。")
    ]


def test_remote_semantic_adapters_send_only_query_vector_and_profile_filter() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/embeddings":
            return httpx.Response(200, json={"data": [{"embedding": [0.8, 0.6]}]})
        if request.url.path == "/collections/memories/points/query":
            return httpx.Response(
                200,
                json={
                    "result": {
                        "points": [
                            {"id": "memory-travel", "score": 0.91},
                        ]
                    }
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    embedding_client = httpx.AsyncClient(
        base_url="https://embedding.example/v1",
        transport=transport,
    )
    index_client = httpx.AsyncClient(
        base_url="https://qdrant.example",
        transport=transport,
    )
    embedding_provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://embedding.example/v1",
        api_key="test-key",
        model="bge-m3",
        client=embedding_client,
    )
    index = QdrantSemanticMemoryIndex(
        base_url="https://qdrant.example",
        collection="memories",
        client=index_client,
    )

    async def run() -> tuple[float, ...]:
        vector = await embedding_provider.embed("杭州行程怎么安排？")
        matches = await index.search(profile_id="profile-a", vector=vector, limit=3)
        assert [(match.record_id, match.score) for match in matches] == [("memory-travel", 0.91)]
        await embedding_client.aclose()
        await index_client.aclose()
        return vector

    assert asyncio.run(run()) == (0.8, 0.6)
    embedding_payload = json.loads(requests[0].content)
    index_payload = json.loads(requests[1].content)
    assert embedding_payload == {"model": "bge-m3", "input": "杭州行程怎么安排？"}
    assert index_payload["query"] == [0.8, 0.6]
    assert index_payload["with_payload"] is False
    assert index_payload["filter"] == {
        "must": [{"key": "profile_id", "match": {"value": "profile-a"}}]
    }
