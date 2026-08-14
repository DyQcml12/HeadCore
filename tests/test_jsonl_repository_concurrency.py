from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.model_audit import text_hash
from app.storage.chat_repository import JsonlChatRepository


def test_concurrent_repository_instances_do_not_lose_or_corrupt_jsonl_records(
    tmp_path: Path,
) -> None:
    storage_dir = tmp_path / "storage"
    worker_count = 32
    records_per_worker = 32

    async def write_worker(worker: int) -> None:
        repository = JsonlChatRepository(storage_dir)
        for index in range(records_per_worker):
            content = f"worker-{worker:02d}-record-{index:02d}-" + "x" * 2048
            await repository.save_memory(
                user_id=f"user-{worker:02d}",
                session_id=f"session-{worker:02d}",
                memory_type="concurrency_probe",
                content=content,
            )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(lambda worker: asyncio.run(write_worker(worker)), range(worker_count)))

    lines = (storage_dir / "memories.jsonl").read_text(encoding="utf-8").splitlines()
    records = []
    invalid_lines = 0
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            invalid_lines += 1

    expected_count = worker_count * records_per_worker
    assert invalid_lines == 0
    assert len(records) == expected_count
    assert len({record["content"] for record in records}) == expected_count
    assert all(record["content_hash"] == text_hash(record["content"]) for record in records)


def test_concurrent_repository_instances_create_one_logical_session(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    worker_count = 64
    ready = threading.Barrier(worker_count)

    def ensure_session(_: int) -> str:
        repository = JsonlChatRepository(storage_dir)
        ready.wait()
        record = asyncio.run(
            repository.ensure_session(user_id="shared-user", client_session_id="shared-session")
        )
        return record.id

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        session_ids = list(executor.map(ensure_session, range(worker_count)))

    lines = (storage_dir / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]

    assert len(set(session_ids)) == 1
    assert len(records) == 1
    assert records[0]["user_id"] == "shared-user"
    assert records[0]["client_session_id"] == "shared-session"


def test_memory_delete_does_not_overwrite_concurrent_appends(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    memories_path = storage_dir / "memories.jsonl"
    storage_dir.mkdir(parents=True)
    fixture_records = [
        {
            "id": "delete-me" if index == 0 else f"fixture-{index}",
            "user_id": "owner",
            "session_id": "fixture-session",
            "memory_type": "fixture",
            "content": "f" * 2048,
            "content_hash": text_hash("f" * 2048),
            "source_message_id": None,
            "confidence": None,
            "created_at": "2026-07-29T00:00:00.000+00:00",
            "updated_at": "2026-07-29T00:00:00.000+00:00",
        }
        for index in range(2000)
    ]
    memories_path.write_text(
        "".join(json.dumps(record) + "\n" for record in fixture_records),
        encoding="utf-8",
    )
    ready = threading.Barrier(2)

    def delete_memory() -> bool:
        ready.wait()
        return asyncio.run(
            JsonlChatRepository(storage_dir).delete_memory(
                user_id="owner",
                memory_id="delete-me",
            )
        )

    def append_memories() -> None:
        repository = JsonlChatRepository(storage_dir)
        ready.wait()

        async def write_all() -> None:
            for index in range(128):
                await repository.save_memory(
                    user_id="writer",
                    session_id="writer-session",
                    memory_type="concurrent_append",
                    content=f"concurrent-{index:03d}",
                )

        asyncio.run(write_all())

    with ThreadPoolExecutor(max_workers=2) as executor:
        deleted = executor.submit(delete_memory)
        appended = executor.submit(append_memories)
        assert deleted.result() is True
        appended.result()

    records = [
        json.loads(line)
        for line in memories_path.read_text(encoding="utf-8").splitlines()
    ]
    appended_contents = {
        record["content"]
        for record in records
        if record.get("memory_type") == "concurrent_append"
    }

    assert all(record["id"] != "delete-me" for record in records)
    assert appended_contents == {f"concurrent-{index:03d}" for index in range(128)}
