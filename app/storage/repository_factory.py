from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.storage.chat_repository import ChatRepository, JsonlChatRepository
from app.storage.postgres_repository import PostgreSQLChatRepository


def create_chat_repository(settings: Settings) -> ChatRepository:
    backend = settings.storage_backend.strip().lower()
    if backend == "jsonl":
        return JsonlChatRepository(Path(settings.jsonl_storage_dir))
    if backend in {"postgres", "postgresql"}:
        return PostgreSQLChatRepository(settings)
    raise ValueError(f"Unsupported STORAGE_BACKEND={settings.storage_backend}")
