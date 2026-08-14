from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.config import load_settings
from app.database_control.contracts import ProfileFilters
from app.database_control.integration_guard import validate_isolated_test_database
from app.database_control.mysql_adapter import MySQLDatabaseControlAdapter
from app.storage.v2_mysql_repository import MySQLDatabaseV2Repository


def test_database_control_real_mysql_read_contract() -> None:
    database_name = os.getenv("DATABASE_CONTROL_TEST_DATABASE", "").strip()
    if not database_name:
        pytest.skip("DATABASE_CONTROL_TEST_DATABASE is not configured")
    validate_isolated_test_database(database_name)

    base_settings = load_settings()
    if not base_settings.mysql_user or not base_settings.mysql_password:
        pytest.skip("isolated MySQL credentials are not configured")
    settings = replace(
        base_settings,
        mysql_database=database_name,
        database_v2_enabled=True,
    )
    adapter = MySQLDatabaseControlAdapter(
        settings,
        MySQLDatabaseV2Repository(settings),
    )

    status = asyncio.run(adapter.get_status())
    page = asyncio.run(
        adapter.list_profiles(filters=ProfileFilters(), limit=2, cursor=None)
    )

    assert status.database == database_name
    assert status.required_tables["profiles"] is True
    assert len(page.items) <= 2


def test_database_v2_binds_fake_qq_and_wechat_accounts_to_one_profile() -> None:
    database_name = os.getenv("DATABASE_CONTROL_TEST_DATABASE", "").strip()
    if not database_name:
        pytest.skip("DATABASE_CONTROL_TEST_DATABASE is not configured")
    validate_isolated_test_database(database_name)
    base_settings = load_settings()
    if not base_settings.mysql_user or not base_settings.mysql_password:
        pytest.skip("isolated MySQL credentials are not configured")
    settings = replace(
        base_settings,
        mysql_database=database_name,
        database_v2_enabled=True,
    )
    repository = MySQLDatabaseV2Repository(settings)
    suffix = uuid4().hex[:12]
    qq_user_id = f"fake_qq_{suffix}"
    wechat_user_id = f"fake_wx_{suffix}"

    async def scenario() -> None:
        qq_before = await repository.resolve_relationship_context(
            platform="qq",
            platform_user_id=qq_user_id,
            display_name="Fake QQ User",
        )
        wechat_before = await repository.resolve_relationship_context(
            platform="wechat",
            platform_user_id=wechat_user_id,
            display_name="Fake Wechat User",
        )
        source_profile_id = qq_before.profile.id
        merged_profile_id = wechat_before.profile.id
        assert source_profile_id != merged_profile_id
        try:
            bound_profile_id = await repository.bind_accounts(
                source_platform="qq",
                source_platform_user_id=qq_user_id,
                target_platform="wechat",
                target_platform_user_id=wechat_user_id,
                changed_by_profile_id=source_profile_id,
                reason="isolated two-platform relationship acceptance",
            )
            qq_after = await repository.find_relationship_context(
                platform="qq", platform_user_id=qq_user_id
            )
            wechat_after = await repository.find_relationship_context(
                platform="wechat", platform_user_id=wechat_user_id
            )

            assert bound_profile_id == source_profile_id
            assert qq_after is not None
            assert wechat_after is not None
            assert qq_after.profile.id == wechat_after.profile.id == source_profile_id
            assert qq_after.effective_relationship_type == "normal_friend"
            assert wechat_after.effective_relationship_type == "normal_friend"
        finally:
            await repository._execute(
                "DELETE FROM relationship_events WHERE profile_id IN (%s, %s)",
                (source_profile_id, merged_profile_id),
            )
            await repository._execute(
                "DELETE FROM platform_accounts WHERE platform_user_id IN (%s, %s)",
                (qq_user_id, wechat_user_id),
            )
            await repository._execute(
                "DELETE FROM profiles WHERE id = %s", (merged_profile_id,)
            )
            await repository._execute(
                "DELETE FROM profiles WHERE id = %s", (source_profile_id,)
            )

    asyncio.run(scenario())
