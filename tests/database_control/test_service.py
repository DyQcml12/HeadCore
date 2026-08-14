import asyncio

import pytest

from app.database_control.contracts import ActorIdentity, ProfileFilters, RelationshipUpdateRequest
from app.database_control.errors import DatabaseNotReadyError, ForbiddenError, ResourceNotFoundError
from app.database_control.service import DatabaseControlService
from tests.database_control.fakes import FakeDatabaseControlRepository, actor


def test_service_resolves_actor_and_redacts_account_identifiers() -> None:
    repository = FakeDatabaseControlRepository(actor())
    service = DatabaseControlService(repository)
    identity = ActorIdentity(platform="qq", platform_user_id="10001")

    resolved = asyncio.run(service.resolve_read_actor(identity))
    admin = asyncio.run(service.get_admin(resolved))
    detail = asyncio.run(service.get_profile(resolved, "profile-user"))

    assert repository.last_identity == identity
    assert admin.accounts[0].platform_user_id == "12*****89"
    assert admin.accounts[0].platform_group_id == "<redacted>"
    assert detail.platform_accounts[0].platform_user_id == "12*****89"


def test_service_rejects_non_admin_actor() -> None:
    service = DatabaseControlService(FakeDatabaseControlRepository(actor("normal_friend")))
    with pytest.raises(ForbiddenError):
        asyncio.run(service.resolve_read_actor(ActorIdentity(platform="qq", platform_user_id="10002")))


def test_service_raises_not_found_for_missing_profile() -> None:
    service = DatabaseControlService(FakeDatabaseControlRepository(actor()))
    with pytest.raises(ResourceNotFoundError):
        asyncio.run(service.get_profile(actor(), "missing"))


def test_service_forwards_typed_pagination_filters() -> None:
    repository = FakeDatabaseControlRepository(actor())
    service = DatabaseControlService(repository)
    filters = ProfileFilters(relationship_type="normal_friend", platform="wechat", query="测试")

    page = asyncio.run(
        service.list_profiles(actor(), filters=filters, limit=25, cursor="cursor-1")
    )

    assert page.next_cursor == "cursor-2"
    assert repository.last_filters == filters


def test_service_lists_safe_control_audits_for_admin_only() -> None:
    service = DatabaseControlService(FakeDatabaseControlRepository(actor()))

    events = asyncio.run(service.list_control_operations(actor(), limit=10))

    assert events[0].audit_id == "audit-1"
    assert not hasattr(events[0], "platform_user_id")
    with pytest.raises(ForbiddenError):
        asyncio.run(service.list_control_operations(actor("normal_friend"), limit=10))


def test_service_rejects_write_when_database_is_not_ready() -> None:
    repository = FakeDatabaseControlRepository(actor(), ready=False)
    service = DatabaseControlService(repository)
    with pytest.raises(DatabaseNotReadyError):
        asyncio.run(
            service.set_profile_relationship(
                actor(),
                "profile-user",
                RelationshipUpdateRequest(
                    relationship_type="blocked",
                    verified=True,
                    reason="confirmed spam",
                ),
            )
        )
    assert repository.write_attempts == [
        ("set_profile_relationship", "rejected", "database_not_ready")
    ]
