import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.identity import AuthenticationRequiredError, CsrfValidationError, resolve_web_identity
from app.auth.service import AuthenticationError, StoredSession


class FakeAuthService:
    async def require_session(self, *, session_token: str | None, **_kwargs: object) -> StoredSession:
        if session_token != "valid-session-cookie":
            raise AuthenticationError("invalid")
        return StoredSession(
            id="server-session-1",
            user_id="web-user-1",
            profile_id="profile-from-session",
            token_hash="x" * 64,
            csrf_secret_hash="y" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked_at=None,
        )


def test_public_auth_identity_ignores_frontend_user_and_session_ids() -> None:
    identity = asyncio.run(
        resolve_web_identity(
            auth_service=FakeAuthService(),
            public_auth_enabled=True,
            session_token="valid-session-cookie",
            supplied_user_id="attacker-profile",
            supplied_session_id="attacker-session",
        )
    )

    assert identity.profile_id == "profile-from-session"
    assert identity.session_id == "server-session-1"


def test_public_auth_identity_rejects_missing_cookie() -> None:
    with pytest.raises(AuthenticationRequiredError, match="authentication required"):
        asyncio.run(
            resolve_web_identity(
                auth_service=FakeAuthService(),
                public_auth_enabled=True,
                session_token=None,
                supplied_user_id="attacker-profile",
                supplied_session_id="attacker-session",
            )
        )


def test_public_auth_identity_for_write_requires_csrf_token() -> None:
    class CsrfCheckingAuthService(FakeAuthService):
        async def require_session(self, *, session_token: str | None, **kwargs: object) -> StoredSession:
            if kwargs.get("csrf_token") != "csrf-value" or kwargs.get("require_csrf") is not True:
                raise AuthenticationError("csrf validation failed")
            return await super().require_session(session_token=session_token)

    with pytest.raises(CsrfValidationError, match="csrf validation failed"):
        asyncio.run(
            resolve_web_identity(
                auth_service=CsrfCheckingAuthService(),
                public_auth_enabled=True,
                session_token="valid-session-cookie",
                csrf_token=None,
                require_csrf=True,
                supplied_user_id="attacker-profile",
                supplied_session_id="attacker-session",
            )
        )


def test_local_development_identity_keeps_existing_compatibility_path() -> None:
    identity = asyncio.run(
        resolve_web_identity(
            auth_service=None,
            public_auth_enabled=False,
            session_token=None,
            supplied_user_id="local-user",
            supplied_session_id="local-session",
        )
    )

    assert identity.profile_id == "local-user"
    assert identity.session_id == "local-session"
