from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

from app.core.config import load_settings
from app.database_control.persona_persistence import PersonaDraftRow
from app.persona_management.mysql_store import MySQLPersonaPersistenceStore


class RecordingStore(MySQLPersonaPersistenceStore):
    def __init__(self) -> None:
        super().__init__(
            replace(
                load_settings(),
                mysql_database="test_persona",
                mysql_user="test",
                mysql_password="test",
            )
        )
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.fetchone_result = None

    async def _execute(self, sql, params):  # type: ignore[no-untyped-def]
        self.statements.append((sql, params))
        return 1

    async def _fetchone(self, sql, params):  # type: ignore[no-untyped-def]
        self.statements.append((sql, params))
        return self.fetchone_result

    async def _fetchall(self, sql, params):  # type: ignore[no-untyped-def]
        self.statements.append((sql, params))
        return []


def test_mysql_persona_store_creates_draft_against_v2003_table() -> None:
    store = RecordingStore()
    now = datetime.now(timezone.utc)
    draft = PersonaDraftRow(
        draft_id="draft-1",
        profile_id="xiaohe_v1",
        definition_json='{"profile_id":"xiaohe_v1"}',
        status="draft",
        created_by_profile_id="profile-admin",
        created_at=now,
    )

    assert asyncio.run(store.create_draft(draft)) == draft
    sql, params = store.statements[0]
    assert "INSERT INTO persona_management_drafts" in sql
    assert params[:2] == ("draft-1", "xiaohe_v1")


def test_mysql_persona_store_reads_active_release_only() -> None:
    store = RecordingStore()
    asyncio.run(store.get_active_release("xiaohe_v1"))

    sql, params = store.statements[0]
    assert "status = 'active'" in sql
    assert params == ("xiaohe_v1",)


def test_mysql_persona_store_reports_durable_backend() -> None:
    store = RecordingStore()
    assert store.durable is True
    assert store.backend_name == "mysql-v2-persona-management"
