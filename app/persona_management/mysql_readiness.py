from __future__ import annotations

from app.core.config import Settings
from app.persona_management.readiness import (
    PERSONA_MANAGEMENT_REQUIRED_TABLES,
    PERSONA_MANAGEMENT_SCHEMA_VERSION,
    PersonaManagementPersistenceStatus,
    assess_persona_management_persistence,
)
from app.storage.mysql_repository import MySQLChatRepository


class MySQLPersonaManagementReadiness(MySQLChatRepository):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)

    async def get_status(self) -> PersonaManagementPersistenceStatus:
        tables = tuple(sorted(PERSONA_MANAGEMENT_REQUIRED_TABLES))
        placeholders = ", ".join("%s" for _table in tables)
        rows = await self._fetchall(
            f"""
            SELECT TABLE_NAME FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ({placeholders})
            """,
            (self.settings.mysql_database, *tables),
        )
        migration = await self._fetchone(
            "SELECT version FROM schema_migrations WHERE version = %s LIMIT 1",
            (PERSONA_MANAGEMENT_SCHEMA_VERSION,),
        )
        return assess_persona_management_persistence(
            {str(row["TABLE_NAME"]) for row in rows},
            migration_applied=migration is not None,
            database_v2_enabled=self.settings.database_v2_enabled,
        )
