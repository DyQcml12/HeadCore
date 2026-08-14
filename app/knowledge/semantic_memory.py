from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

import httpx

from app.knowledge.models import MemoryProjection
from app.knowledge.runtime import MemoryProjectionProvider, MemoryProjectionRequest


DEFAULT_SEMANTIC_MEMORY_LIMIT = 8
DEFAULT_SEMANTIC_MEMORY_MIN_SCORE = 0.35


class SemanticMemoryIndexUnavailableError(RuntimeError):
    """Raised when a derived semantic index cannot serve a query."""


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> tuple[float, ...]: ...


@dataclass(frozen=True)
class SemanticMemoryMatch:
    record_id: str
    score: float


class SemanticMemoryIndex(Protocol):
    async def search(
        self,
        *,
        profile_id: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[SemanticMemoryMatch, ...]: ...


class OpenAICompatibleEmbeddingProvider:
    """Minimal remote embedding adapter; keys remain in process configuration."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not api_key.strip() or not model.strip():
            raise ValueError("embedding base_url, api_key, and model are required")
        self._model = model.strip()
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key.strip()}"},
        )
        if client is not None:
            self._client.headers.setdefault("Authorization", f"Bearer {api_key.strip()}")

    async def embed(self, text: str) -> tuple[float, ...]:
        query = text.strip()
        if not query:
            raise ValueError("embedding text must not be blank")
        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self._model, "input": query},
            )
            response.raise_for_status()
            payload = response.json()
            raw_vector = payload["data"][0]["embedding"]
            vector = tuple(float(value) for value in raw_vector)
            _validate_vector(vector)
            return vector
        except (KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
            raise SemanticMemoryIndexUnavailableError("embedding_unavailable") from exc


class LocalSentenceTransformerEmbeddingProvider:
    """Loads a pre-downloaded embedding model from disk without network fallback."""

    def __init__(
        self,
        *,
        model_path: str,
        device: str = "cpu",
        max_length: int = 8192,
    ) -> None:
        path = Path(model_path).expanduser()
        if not path.is_dir():
            raise ValueError("local embedding model_path must be an existing directory")
        if not device.strip():
            raise ValueError("local embedding device is required")
        if not 1 <= max_length <= 8192:
            raise ValueError("local embedding max_length must be between 1 and 8192")
        self._model_path = path
        self._device = device.strip()
        self._max_length = max_length
        self._model: object | None = None
        self._load_lock = Lock()

    async def embed(self, text: str) -> tuple[float, ...]:
        query = text.strip()
        if not query:
            raise ValueError("embedding text must not be blank")
        try:
            return await asyncio.to_thread(self._embed_sync, query)
        except SemanticMemoryIndexUnavailableError:
            raise
        except Exception as exc:
            raise SemanticMemoryIndexUnavailableError("local_embedding_unavailable") from exc

    def _embed_sync(self, query: str) -> tuple[float, ...]:
        model = self._get_model()
        try:
            encoded = model.encode(  # type: ignore[attr-defined]
                query,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            vector = tuple(float(value) for value in encoded.tolist())
            _validate_vector(vector)
            return vector
        except (AttributeError, TypeError, ValueError) as exc:
            raise SemanticMemoryIndexUnavailableError("local_embedding_unavailable") from exc

    def _get_model(self) -> object:
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    str(self._model_path),
                    device=self._device,
                    trust_remote_code=False,
                )
                model.max_seq_length = self._max_length
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                raise SemanticMemoryIndexUnavailableError("local_embedding_unavailable") from exc
            self._model = model
            return model


class QdrantSemanticMemoryIndex:
    """Qdrant is a derived index and never returns memory content as authority."""

    def __init__(
        self,
        *,
        base_url: str,
        collection: str,
        api_key: str = "",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not collection.strip():
            raise ValueError("qdrant base_url and collection are required")
        self._collection = collection.strip()
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"api-key": api_key.strip()} if api_key.strip() else None,
        )
        if client is not None and api_key.strip():
            self._client.headers.setdefault("api-key", api_key.strip())

    async def search(
        self,
        *,
        profile_id: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[SemanticMemoryMatch, ...]:
        if not profile_id.strip():
            raise ValueError("profile_id is required")
        _validate_vector(vector)
        if limit <= 0:
            return ()
        try:
            response = await self._client.post(
                f"/collections/{self._collection}/points/query",
                json={
                    "query": list(vector),
                    "limit": limit,
                    "with_payload": False,
                    "filter": {
                        "must": [
                            {"key": "profile_id", "match": {"value": profile_id.strip()}},
                        ]
                    },
                },
            )
            response.raise_for_status()
            points = response.json()["result"]["points"]
            matches = tuple(
                SemanticMemoryMatch(record_id=str(point["id"]), score=float(point["score"]))
                for point in points
            )
            if any(not item.record_id or not math.isfinite(item.score) for item in matches):
                raise ValueError("invalid semantic index result")
            return matches
        except (KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
            raise SemanticMemoryIndexUnavailableError("qdrant_unavailable") from exc

    async def ensure_collection(self, *, vector_size: int) -> None:
        if not 1 <= vector_size <= 4096:
            raise ValueError("qdrant vector_size must be between 1 and 4096")
        try:
            response = await self._client.get(f"/collections/{self._collection}")
            if response.status_code == 404:
                response = await self._client.put(
                    f"/collections/{self._collection}",
                    json={
                        "vectors": {
                            "size": vector_size,
                            "distance": "Cosine",
                        }
                    },
                )
                response.raise_for_status()
            else:
                response.raise_for_status()
                configured_size = int(response.json()["result"]["config"]["params"]["vectors"]["size"])
                if configured_size != vector_size:
                    raise ValueError("qdrant collection vector size does not match embedding model")
            response = await self._client.put(
                f"/collections/{self._collection}/index?wait=true",
                json={"field_name": "profile_id", "field_schema": "keyword"},
            )
            response.raise_for_status()
        except (KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
            raise SemanticMemoryIndexUnavailableError("qdrant_unavailable") from exc

    async def upsert(
        self,
        *,
        record_id: str,
        profile_id: str,
        vector: tuple[float, ...],
        revision: str = "",
    ) -> None:
        if not record_id.strip() or not profile_id.strip():
            raise ValueError("record_id and profile_id are required")
        _validate_vector(vector)
        try:
            response = await self._client.put(
                f"/collections/{self._collection}/points?wait=true",
                json={
                    "points": [
                        {
                            "id": record_id,
                            "vector": list(vector),
                            "payload": {
                                "profile_id": profile_id,
                                "revision": revision,
                            },
                        }
                    ]
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SemanticMemoryIndexUnavailableError("qdrant_unavailable") from exc

    async def remove(self, *, record_id: str) -> None:
        if not record_id.strip():
            raise ValueError("record_id is required")
        try:
            response = await self._client.post(
                f"/collections/{self._collection}/points/delete?wait=true",
                json={"points": [record_id]},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SemanticMemoryIndexUnavailableError("qdrant_unavailable") from exc


@dataclass(frozen=True)
class _InMemoryPoint:
    profile_id: str
    vector: tuple[float, ...]


class InMemorySemanticMemoryIndex:
    """Deterministic index used by tests and offline contract checks."""

    def __init__(self) -> None:
        self._points: dict[str, _InMemoryPoint] = {}

    async def upsert(
        self,
        *,
        record_id: str,
        profile_id: str,
        vector: tuple[float, ...],
        revision: str = "",
    ) -> None:
        if not record_id.strip() or not profile_id.strip():
            raise ValueError("record_id and profile_id are required")
        _validate_vector(vector)
        self._points[record_id] = _InMemoryPoint(profile_id=profile_id, vector=vector)

    async def remove(self, *, record_id: str) -> None:
        self._points.pop(record_id, None)

    async def search(
        self,
        *,
        profile_id: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[SemanticMemoryMatch, ...]:
        _validate_vector(vector)
        if limit <= 0:
            return ()
        matches = [
            SemanticMemoryMatch(record_id=record_id, score=_cosine_similarity(vector, point.vector))
            for record_id, point in self._points.items()
            if point.profile_id == profile_id and len(point.vector) == len(vector)
        ]
        matches.sort(key=lambda match: (-match.score, match.record_id))
        return tuple(matches[:limit])


class SemanticMemoryProjectionProvider:
    """Uses a derived vector index without bypassing canonical memory policy."""

    def __init__(
        self,
        authoritative_provider: MemoryProjectionProvider,
        *,
        index: SemanticMemoryIndex,
        embedding_provider: EmbeddingProvider,
        limit: int = DEFAULT_SEMANTIC_MEMORY_LIMIT,
        min_score: float = DEFAULT_SEMANTIC_MEMORY_MIN_SCORE,
    ) -> None:
        if limit <= 0:
            raise ValueError("semantic memory limit must be positive")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError("semantic memory minimum score must be between 0 and 1")
        self._authoritative_provider = authoritative_provider
        self._index = index
        self._embedding_provider = embedding_provider
        self._limit = limit
        self._min_score = min_score

    async def get_projection(
        self,
        request: MemoryProjectionRequest,
    ) -> tuple[MemoryProjection, ...]:
        authoritative = await self._authoritative_provider.get_projection(request)
        query = request.query.strip()
        if not authoritative or not query:
            return authoritative
        try:
            vector = await self._embedding_provider.embed(query)
            _validate_vector(vector)
            matches = await self._index.search(
                profile_id=request.profile_id,
                vector=vector,
                limit=self._limit,
            )
        except (SemanticMemoryIndexUnavailableError, ValueError):
            return authoritative
        except Exception:
            return authoritative

        by_record_id = {item.record_id: item for item in authoritative}
        selected = [
            by_record_id[match.record_id]
            for match in matches
            if match.score >= self._min_score and match.record_id in by_record_id
        ]
        return tuple(selected)


def _validate_vector(vector: tuple[float, ...]) -> None:
    if not vector or len(vector) > 4096:
        raise ValueError("embedding vector must contain 1 to 4096 dimensions")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("embedding vector must contain only finite values")
    if not any(value != 0.0 for value in vector):
        raise ValueError("embedding vector cannot be all zero")


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm)
