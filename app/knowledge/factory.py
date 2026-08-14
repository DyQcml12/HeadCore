from __future__ import annotations

from app.core.config import Settings
from app.knowledge.mysql_repository import MySQLKnowledgeRepository
from app.knowledge.runtime import (
    LifecycleMemoryProjectionProvider,
    MemoryProjectionProvider,
    ReadinessCheckedMemoryProjectionProvider,
)
from app.knowledge.semantic_memory import (
    EmbeddingProvider,
    LocalSentenceTransformerEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    QdrantSemanticMemoryIndex,
    SemanticMemoryProjectionProvider,
)
from app.knowledge.semantic_outbox import SemanticMemoryOutboxProcessor
from app.knowledge.service import KnowledgeLifecycleService


def build_memory_projection_provider(settings: Settings) -> MemoryProjectionProvider | None:
    if not settings.database_v2_enabled:
        return None
    if not settings.mysql_database or not settings.mysql_user or not settings.mysql_password:
        return None
    repository = MySQLKnowledgeRepository(settings)
    provider = LifecycleMemoryProjectionProvider(KnowledgeLifecycleService(repository))
    authoritative_provider = ReadinessCheckedMemoryProjectionProvider(repository, provider)
    if not _semantic_memory_is_configured(settings):
        return authoritative_provider
    return SemanticMemoryProjectionProvider(
        authoritative_provider,
        index=QdrantSemanticMemoryIndex(
            base_url=settings.semantic_memory_qdrant_url,
            api_key=settings.semantic_memory_qdrant_api_key,
            collection=settings.semantic_memory_qdrant_collection,
        ),
        embedding_provider=_build_embedding_provider(settings),
        limit=settings.semantic_memory_retrieval_limit,
        min_score=settings.semantic_memory_min_score,
    )


def _semantic_memory_is_configured(settings: Settings) -> bool:
    if not (
        settings.semantic_memory_enabled
        and settings.semantic_memory_qdrant_url.strip()
        and settings.semantic_memory_qdrant_collection.strip()
    ):
        return False
    provider = settings.semantic_memory_embedding_provider.strip().lower()
    if provider == "local_sentence_transformer":
        return bool(settings.semantic_memory_embedding_model_path.strip())
    if provider == "openai_compatible":
        return bool(
            settings.semantic_memory_embedding_base_url.strip()
            and settings.semantic_memory_embedding_api_key.strip()
            and settings.semantic_memory_embedding_model.strip()
        )
    return False


def _build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.semantic_memory_embedding_provider.strip().lower()
    if provider == "local_sentence_transformer":
        return LocalSentenceTransformerEmbeddingProvider(
            model_path=settings.semantic_memory_embedding_model_path,
            device=settings.semantic_memory_embedding_device,
            max_length=settings.semantic_memory_embedding_max_length,
        )
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            base_url=settings.semantic_memory_embedding_base_url,
            api_key=settings.semantic_memory_embedding_api_key,
            model=settings.semantic_memory_embedding_model,
            timeout_seconds=settings.semantic_memory_embedding_timeout_seconds,
        )
    raise ValueError(f"Unsupported semantic memory embedding provider: {provider}")


def build_semantic_memory_outbox_processor(
    settings: Settings,
    *,
    worker_id: str,
) -> SemanticMemoryOutboxProcessor | None:
    if not _semantic_memory_is_configured(settings):
        return None
    if not settings.database_v2_enabled:
        return None
    if not settings.mysql_database or not settings.mysql_user or not settings.mysql_password:
        return None
    return SemanticMemoryOutboxProcessor(
        MySQLKnowledgeRepository(settings),
        index=QdrantSemanticMemoryIndex(
            base_url=settings.semantic_memory_qdrant_url,
            api_key=settings.semantic_memory_qdrant_api_key,
            collection=settings.semantic_memory_qdrant_collection,
        ),
        embedding_provider=_build_embedding_provider(settings),
        worker_id=worker_id,
    )
