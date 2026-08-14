import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.passwords import hash_password
from app.auth.audit import AuthAuditEvent
from app.auth.mysql_repository import MySQLAuthRepository
from app.auth.service import AuthService, AuthenticationError, StoredSession, WebUser
from app.core.config import load_settings


class FakeAuthRepository:
    def __init__(self) -> None:
        self.user = WebUser(
            id="user-1",
            profile_id="profile-1",
            email_normalized="reader@example.com",
            password_hash=hash_password("SafePassword!2026"),
            status="active",
        )
        self.created: dict[str, object] | None = None
        self.session: StoredSession | None = None

    async def find_user_by_email(self, *, email_normalized: str) -> WebUser | None:
        return self.user if email_normalized == self.user.email_normalized else None

    async def create_session(self, **values: object) -> StoredSession:
        self.created = values
        self.session = StoredSession(
            id="session-1",
            user_id=str(values["user_id"]),
            profile_id="profile-1",
            token_hash=str(values["token_hash"]),
            csrf_secret_hash=str(values["csrf_secret_hash"]),
            expires_at=values["expires_at"],  # type: ignore[arg-type]
            revoked_at=None,
        )
        return self.session

    async def find_session_by_token_hash(self, *, token_hash: str) -> StoredSession | None:
        return self.session if self.session and self.session.token_hash == token_hash else None

    async def revoke_session(self, *, session_id: str, revoked_at: datetime) -> None:
        assert self.session is not None
        assert session_id == self.session.id
        self.session = StoredSession(**{**self.session.__dict__, "revoked_at": revoked_at})


def test_login_creates_hashed_server_side_session() -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository, session_lifetime=timedelta(hours=2))
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)

    authenticated = asyncio.run(
        service.login(email=" Reader@Example.com ", password="SafePassword!2026", now=now)
    )

    assert authenticated.user_id == "user-1"
    assert authenticated.profile_id == "profile-1"
    assert repository.created is not None
    assert authenticated.session_token not in str(repository.created)
    assert authenticated.csrf_token not in str(repository.created)
    assert authenticated.expires_at == now + timedelta(hours=2)


def test_login_uses_one_public_error_for_unknown_or_wrong_password() -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository)

    with pytest.raises(AuthenticationError, match="invalid email or password"):
        asyncio.run(service.login(email="missing@example.com", password="SafePassword!2026"))
    with pytest.raises(AuthenticationError, match="invalid email or password"):
        asyncio.run(service.login(email="reader@example.com", password="WrongPassword!2026"))


def test_current_session_requires_matching_csrf_for_write_operations() -> None:
    repository = FakeAuthRepository()
    service = AuthService(repository)
    authenticated = asyncio.run(
        service.login(email="reader@example.com", password="SafePassword!2026")
    )

    current = asyncio.run(
        service.require_session(
            session_token=authenticated.session_token,
            csrf_token=authenticated.csrf_token,
            require_csrf=True,
        )
    )
    assert current.profile_id == "profile-1"

    with pytest.raises(AuthenticationError, match="csrf validation failed"):
        asyncio.run(
            service.require_session(
                session_token=authenticated.session_token,
                csrf_token="invalid",
                require_csrf=True,
            )
        )


class RecordingMySQLAuthRepository(MySQLAuthRepository):
    def __init__(self) -> None:
        settings = load_settings()
        object.__setattr__(settings, "mysql_database", "hutao_chat_core")
        object.__setattr__(settings, "mysql_user", "test-user")
        object.__setattr__(settings, "mysql_password", "test-password")
        super().__init__(settings)
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.row: dict[str, object] | None = None

    async def _fetchone(self, sql: str, params: tuple[object, ...]):  # type: ignore[override]
        self.statements.append((sql, params))
        return self.row

    async def _execute(self, sql: str, params: tuple[object, ...]) -> int:  # type: ignore[override]
        self.statements.append((sql, params))
        return 1


def test_mysql_auth_repository_uses_parameterized_hash_lookups() -> None:
    repository = RecordingMySQLAuthRepository()
    repository.row = {
        "id": "user-1",
        "profile_id": "profile-1",
        "email_normalized": "reader@example.com",
        "password_hash": "$argon2id$example",
        "status": "active",
    }

    user = asyncio.run(repository.find_user_by_email(email_normalized="reader@example.com"))

    assert user is not None
    assert user.profile_id == "profile-1"
    sql, params = repository.statements[0]
    assert "WHERE email_normalized = %s" in sql
    assert params == ("reader@example.com",)


def test_mysql_auth_repository_maps_the_active_current_account() -> None:
    repository = RecordingMySQLAuthRepository()
    repository.row = {
        "user_id": "user-1",
        "profile_id": "profile-1",
        "display_name": "往生堂访客",
        "email_normalized": "reader@example.com",
        "email_verified_at": datetime(2026, 7, 26, 1, 30),
        "created_at": datetime(2026, 7, 25, 8, 0),
    }

    account = asyncio.run(repository.find_account_by_user_id(user_id="user-1"))

    assert account is not None
    assert account.profile_id == "profile-1"
    assert account.display_name == "往生堂访客"
    assert account.email_normalized == "reader@example.com"
    assert account.email_verified is True
    assert account.created_at == datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
    sql, params = repository.statements[0]
    assert "wu.status = 'active'" in sql
    assert "p.status = 'active'" in sql
    assert params == ("user-1",)


def test_mysql_auth_repository_writes_only_hashes_for_session() -> None:
    repository = RecordingMySQLAuthRepository()
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)

    asyncio.run(
        repository.create_session(
            user_id="user-1",
            token_hash="a" * 64,
            csrf_secret_hash="b" * 64,
            expires_at=now + timedelta(days=1),
            created_at=now,
        )
    )

    sql, params = repository.statements[0]
    assert "INSERT INTO web_sessions" in sql
    assert "a" * 64 in params
    assert "b" * 64 in params
    assert all("SafePassword" not in str(value) for value in params)


def test_mysql_auth_repository_records_redacted_audit_event() -> None:
    repository = RecordingMySQLAuthRepository()

    asyncio.run(
        repository.record(
            AuthAuditEvent(
                event_type="login_succeeded",
                outcome="accepted",
                reason_code="session_created",
                user_id="user-1",
            )
        )
    )

    sql, params = repository.statements[0]
    assert "INSERT INTO auth_audit_events" in sql
    assert "user-1" in params
    assert all("SafePassword" not in str(value) for value in params)
