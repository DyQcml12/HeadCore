from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import load_settings
from app.core.security import redact_secrets
from app.storage.chat_repository import JsonlChatRepository
from app.storage.mysql_repository import MySQLChatRepository
from app.storage.repository_factory import create_chat_repository


class RecordingMySQLRepository(MySQLChatRepository):
    def __init__(self) -> None:
        settings = load_settings()
        object.__setattr__(settings, "mysql_database", "hutao_chat")
        object.__setattr__(settings, "mysql_user", "hutao_user")
        object.__setattr__(settings, "mysql_password", "password-from-env")
        super().__init__(settings)
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.existing_session: dict[str, object] | None = None
        self.fetchone_results: list[dict[str, object] | None] = []

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:
        self.statements.append((sql, params))
        return 1

    async def _fetchone(
        self, sql: str, params: tuple[object, ...]
    ) -> dict[str, object] | None:
        self.statements.append((sql, params))
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return self.existing_session

    async def _fetchall(
        self, sql: str, params: tuple[object, ...]
    ) -> list[dict[str, object]]:
        self.statements.append((sql, params))
        return []


def test_secret_redaction() -> None:
    text = redact_secrets("token=sk-" + ("2" * 30))

    assert "sk-" not in text
    assert "<REDACTED_API_KEY>" in text


def test_jsonl_repository_deletes_only_owner_memory(tmp_path: Path) -> None:
    repository = JsonlChatRepository(tmp_path / "storage")
    own_memory = asyncio.run(
        repository.save_memory(
            user_id="u1",
            session_id="s1",
            memory_type="conversation_preference",
            content="回复风格=短句",
        )
    )
    other_memory = asyncio.run(
        repository.save_memory(
            user_id="u2",
            session_id="s2",
            memory_type="user_alias",
            content="称呼=阿明",
        )
    )

    deleted_wrong_owner = asyncio.run(
        repository.delete_memory(user_id="u1", memory_id=other_memory.id)
    )
    deleted_own = asyncio.run(repository.delete_memory(user_id="u1", memory_id=own_memory.id))

    assert deleted_wrong_owner is False
    assert deleted_own is True
    assert asyncio.run(repository.list_memories(user_id="u1")) == []
    assert [memory.id for memory in asyncio.run(repository.list_memories(user_id="u2"))] == [
        other_memory.id
    ]


def test_default_storage_backend_is_jsonl(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "jsonl")
    settings = load_settings()

    assert settings.storage_backend == "jsonl"
    assert isinstance(create_chat_repository(settings), JsonlChatRepository)


def test_mysql_configuration_fields_are_loaded(monkeypatch) -> None:
    monkeypatch.setenv("MYSQL_HOST", "db.local")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_DATABASE", "hutao_chat")
    monkeypatch.setenv("MYSQL_USER", "hutao_user")
    monkeypatch.setenv("MYSQL_PASSWORD", "password-from-env")

    settings = load_settings()

    assert settings.mysql_host == "db.local"
    assert settings.mysql_port == 3307
    assert settings.mysql_database == "hutao_chat"
    assert settings.mysql_user == "hutao_user"
    assert settings.mysql_password == "password-from-env"


def test_mysql_repository_writes_core_table_statements() -> None:
    repository = RecordingMySQLRepository()

    session = asyncio.run(
        repository.ensure_session(user_id="user-1", client_session_id="session-1")
    )
    invocation = asyncio.run(
        repository.save_model_invocation(
            session_id=session.id,
            user_id="user-1",
            provider="deepseek",
            model="deepseek-v4-pro",
            used_live_api=True,
            fallback_used=False,
            latency_ms=12.34,
            prompt_hash="a" * 64,
            response_hash="b" * 64,
            error=None,
            request_metadata_json={"api_path": "/api/v1/chat"},
        )
    )
    message = asyncio.run(
        repository.save_message(
            session_id=session.id,
            user_id="user-1",
            role="assistant",
            content="reply",
            model_invocation_id=invocation.id,
        )
    )
    evaluation = asyncio.run(
        repository.save_persona_evaluation(
            message_id=message.id,
            model_invocation_id=invocation.id,
            passed=True,
            score=1.0,
            evaluator_provider="local-rules",
            evaluator_model="hutao-persona-response-gate-v2",
            reasons_json={"reasons": []},
        )
    )
    memory = asyncio.run(
        repository.save_memory(
            user_id="user-1",
            session_id=session.id,
            memory_type="user_alias",
            content="叫我阿明",
            source_message_id=message.id,
            confidence=0.9,
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert "SELECT id, user_id, client_session_id, created_at, updated_at" in executed_sql
    assert "INSERT INTO sessions" in executed_sql
    assert "INSERT INTO model_invocations" in executed_sql
    assert "INSERT INTO messages" in executed_sql
    assert "INSERT INTO persona_evaluations" in executed_sql
    assert "INSERT INTO memories" in executed_sql
    assert message.model_invocation_id == invocation.id
    assert evaluation.message_id == message.id
    assert memory.memory_type == "user_alias"
    assert len(session.id) == 36
    assert len(invocation.id) == 36


def test_mysql_repository_resolves_new_owner_contact() -> None:
    repository = RecordingMySQLRepository()
    repository.fetchone_results = [None]

    contact = asyncio.run(
        repository.resolve_contact(
            platform="qq",
            platform_user_id="10001",
            owner_platform_user_ids={"10001"},
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert contact.relationship_role == "owner"
    assert contact.authority_level == 100
    assert contact.affection_level == 100
    assert "FROM contacts c" in executed_sql
    assert "INSERT INTO contacts" in executed_sql
    assert "INSERT INTO platform_identities" in executed_sql


def test_mysql_repository_writes_relationship_claim_and_update_statements() -> None:
    repository = RecordingMySQLRepository()
    repository.fetchone_results = [None, None]

    claim = asyncio.run(
        repository.save_relationship_claim(
            platform="qq",
            platform_user_id="20002",
            claimed_role="owner_relative",
            claimed_name="阿姐",
            evidence_text="我是主人亲人",
        )
    )
    contact = asyncio.run(
        repository.update_contact_relationship(
            platform="qq",
            platform_user_id="20002",
            relationship_role="owner_relative",
            display_name="阿姐",
            changed_by_platform_user_id="10001",
            reason="owner approved",
        )
    )

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert claim.claimed_role == "owner_relative"
    assert contact.relationship_role == "owner_relative"
    assert "INSERT INTO relationship_claims" in executed_sql
    assert "UPDATE contacts" in executed_sql
    assert "INSERT INTO relationship_events" in executed_sql


def test_mysql_repository_queries_owner_visible_recent_chat_statements() -> None:
    repository = RecordingMySQLRepository()
    repository.fetchone_results = []

    messages = asyncio.run(repository.list_recent_messages_by_user(user_id="qq-20002", limit=12))
    user_ids = asyncio.run(repository.list_recent_user_ids(limit=20))

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert messages == []
    assert user_ids == []
    assert "FROM messages" in executed_sql
    assert "WHERE user_id = %s" in executed_sql
    assert "GROUP BY user_id" in executed_sql


def test_mysql_repository_deletes_memory_by_user_and_id() -> None:
    repository = RecordingMySQLRepository()

    deleted = asyncio.run(repository.delete_memory(user_id="user-1", memory_id="memory-1"))

    executed_sql = "\n".join(sql for sql, _params in repository.statements)
    assert deleted is True
    assert "DELETE FROM memories" in executed_sql
    assert repository.statements[-1][1] == ("memory-1", "user-1")


def test_mysql_repository_uses_asyncmy_cursor_cls_parameter() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "app" / "storage" / "mysql_repository.py").read_text(
        encoding="utf-8"
    )

    assert "cursor_cls=asyncmy.cursors.DictCursor" in source
    assert "cursorclass=" not in source
