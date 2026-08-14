import pytest

from app.database_control.actor import build_actor_identity, require_read_admin
from app.database_control.errors import ForbiddenError, UnauthenticatedError
from tests.database_control.fakes import actor


def test_actor_identity_requires_database_lookup_headers() -> None:
    with pytest.raises(UnauthenticatedError):
        build_actor_identity(platform="qq", platform_user_id="", platform_group_id=None)


def test_read_admin_permission_matrix() -> None:
    require_read_admin(actor())
    for denied_actor in (
        actor("normal_friend"),
        actor("blocked"),
        actor("admin_partner", status="disabled"),
    ):
        with pytest.raises(ForbiddenError):
            require_read_admin(denied_actor)
