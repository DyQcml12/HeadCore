import asyncio
from dataclasses import replace

from app.core.config import load_settings
from app.persona_management.mysql_readiness import MySQLPersonaManagementReadiness
from app.persona_management.readiness import PERSONA_MANAGEMENT_REQUIRED_TABLES


class RecordingReadiness(MySQLPersonaManagementReadiness):
    def __init__(self) -> None:
        super().__init__(replace(
            load_settings(), database_v2_enabled=True,
            mysql_database="test_persona", mysql_user="test", mysql_password="test",
        ))
        self.rows = [{"TABLE_NAME": name} for name in PERSONA_MANAGEMENT_REQUIRED_TABLES]
        self.migration = None

    async def _fetchall(self, sql, params):  # type: ignore[no-untyped-def]
        return self.rows

    async def _fetchone(self, sql, params):  # type: ignore[no-untyped-def]
        return self.migration


def test_mysql_persona_readiness_requires_migration_and_tables() -> None:
    repository = RecordingReadiness()
    assert asyncio.run(repository.get_status()).reason == "persona_management_migration_missing"
    repository.migration = {"version": "v2.003_persona_management"}
    assert asyncio.run(repository.get_status()).write_ready is True
