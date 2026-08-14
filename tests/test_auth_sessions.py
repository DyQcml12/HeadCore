from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.auth.sessions import hash_opaque_token, issue_session, session_is_active


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_issued_session_keeps_only_a_hash_for_persistence() -> None:
    issued = issue_session(now=datetime(2026, 7, 25, tzinfo=timezone.utc), lifetime=timedelta(days=7))

    assert len(issued.token) >= 43
    assert issued.token not in issued.token_hash
    assert issued.token_hash == hash_opaque_token(issued.token)
    assert issued.expires_at == datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_session_is_inactive_when_expired_or_revoked() -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)

    assert session_is_active(expires_at=now + timedelta(minutes=1), revoked_at=None, now=now) is True
    assert session_is_active(expires_at=now, revoked_at=None, now=now) is False
    assert (
        session_is_active(
            expires_at=now + timedelta(minutes=1),
            revoked_at=now - timedelta(seconds=1),
            now=now,
        )
        is False
    )


def test_auth_migration_uses_hashed_tokens_and_profile_foreign_keys() -> None:
    migration = (
        PROJECT_ROOT / "migrations" / "v2" / "004_public_web_auth.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS web_users" in migration
    assert "email_normalized" in migration
    assert "password_hash" in migration
    assert "token_hash CHAR(64) NOT NULL" in migration
    assert "CREATE TABLE IF NOT EXISTS web_sessions" in migration
    assert "revoked_at DATETIME(3) NULL" in migration
    assert "FOREIGN KEY (profile_id) REFERENCES profiles (id)" in migration
    assert "token VARCHAR" not in migration
