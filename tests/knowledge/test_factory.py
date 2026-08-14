from dataclasses import replace

from app.core.config import load_settings
from app.knowledge.factory import (
    build_memory_projection_provider,
    build_semantic_memory_outbox_processor,
)
from app.knowledge.runtime import ReadinessCheckedMemoryProjectionProvider
from app.knowledge.semantic_memory import SemanticMemoryProjectionProvider
from app.knowledge.semantic_outbox import SemanticMemoryOutboxProcessor


def test_factory_is_disabled_without_database_v2() -> None:
    settings = replace(load_settings(), database_v2_enabled=False)
    assert build_memory_projection_provider(settings) is None


def test_factory_requires_complete_mysql_settings() -> None:
    settings = replace(
        load_settings(),
        database_v2_enabled=True,
        mysql_database="test_knowledge",
        mysql_user="",
        mysql_password="",
    )
    assert build_memory_projection_provider(settings) is None


def test_factory_builds_lazy_provider_without_connecting() -> None:
    settings = replace(
        load_settings(),
        database_v2_enabled=True,
        mysql_database="test_knowledge",
        mysql_user="test",
        mysql_password="test",
    )
    assert isinstance(
        build_memory_projection_provider(settings),
        ReadinessCheckedMemoryProjectionProvider,
    )


def test_factory_wraps_authoritative_projection_with_semantic_retrieval_only_when_complete() -> None:
    settings = replace(
        load_settings(),
        database_v2_enabled=True,
        mysql_database="test_knowledge",
        mysql_user="test",
        mysql_password="test",
        semantic_memory_enabled=True,
        semantic_memory_qdrant_url="https://qdrant.example",
        semantic_memory_qdrant_collection="hutao_memories",
        semantic_memory_embedding_base_url="https://embedding.example/v1",
        semantic_memory_embedding_api_key="test-embedding-key",
        semantic_memory_embedding_model="bge-m3",
    )

    assert isinstance(
        build_memory_projection_provider(settings),
        SemanticMemoryProjectionProvider,
    )
    assert isinstance(
        build_semantic_memory_outbox_processor(settings, worker_id="test-worker"),
        SemanticMemoryOutboxProcessor,
    )
