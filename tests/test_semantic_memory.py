from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx

from app.core.config import load_settings
from app.knowledge.factory import _semantic_memory_is_configured
from app.knowledge.semantic_memory import QdrantSemanticMemoryIndex
from app.knowledge.semantic_outbox import SemanticMemoryOutboxProcessor


def test_qdrant_semantic_index_creates_collection_and_profile_payload_index() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404, request=request)
        return httpx.Response(200, json={"result": True}, request=request)

    client = httpx.AsyncClient(
        base_url="http://qdrant.test",
        transport=httpx.MockTransport(handler),
    )
    index = QdrantSemanticMemoryIndex(
        base_url="http://qdrant.test",
        collection="hutao_memories",
        client=client,
    )

    asyncio.run(index.ensure_collection(vector_size=3))
    asyncio.run(client.aclose())

    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/collections/hutao_memories"),
        ("PUT", "/collections/hutao_memories"),
        ("PUT", "/collections/hutao_memories/index"),
    ]
    assert json.loads(requests[1].content) == {"vectors": {"size": 3, "distance": "Cosine"}}
    assert json.loads(requests[2].content) == {"field_name": "profile_id", "field_schema": "keyword"}


def test_semantic_memory_worker_initializes_index_from_embedding_dimension() -> None:
    class FakeRepository:
        async def claim_pending(self, **_kwargs):
            return ()

        async def get_record(self, _record_id):
            return None

        async def mark_completed(self, _event_id):
            return None

        async def reschedule(self, _event_id, *, reason):
            return None

    class FakeEmbeddingProvider:
        async def embed(self, text: str) -> tuple[float, ...]:
            assert text == "semantic memory initialization"
            return (0.1, 0.2, 0.3)

    class FakeIndex:
        vector_sizes: list[int] = []

        async def ensure_collection(self, *, vector_size: int) -> None:
            type(self).vector_sizes.append(vector_size)

        async def upsert(self, **_kwargs) -> None:
            return None

        async def remove(self, **_kwargs) -> None:
            return None

    processor = SemanticMemoryOutboxProcessor(
        FakeRepository(),
        index=FakeIndex(),
        embedding_provider=FakeEmbeddingProvider(),
        worker_id="semantic-test",
    )

    asyncio.run(processor.initialize_index())

    assert FakeIndex.vector_sizes == [3]


def test_local_semantic_memory_configuration_does_not_require_embedding_api_credentials(tmp_path) -> None:
    settings = replace(
        load_settings(),
        semantic_memory_enabled=True,
        semantic_memory_qdrant_url="http://qdrant.test:6333",
        semantic_memory_embedding_provider="local_sentence_transformer",
        semantic_memory_embedding_model_path=str(tmp_path),
        semantic_memory_embedding_base_url="",
        semantic_memory_embedding_api_key="",
        semantic_memory_embedding_model="",
    )

    assert _semantic_memory_is_configured(settings) is True
