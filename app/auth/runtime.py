from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from fastapi import FastAPI

from app.auth.mysql_repository import MySQLAuthRepository
from app.auth.postgres_repository import PostgreSQLAuthRepository
from app.auth.password_reset import PasswordResetService
from app.auth.password_reset_router import create_password_reset_router
from app.auth.registration import RegistrationService
from app.auth.registration_router import create_registration_router
from app.auth.rate_limit import AuthRateLimitService
from app.auth.router import create_auth_router
from app.auth.service import AuthService
from app.auth.smtp_delivery import SmtpEmailSettings, SmtpEmailVerificationDelivery
from app.core.config import Settings
from app.storage.postgres_repository import postgres_is_configured


@dataclass(frozen=True)
class PublicWebAuthRuntime:
    authentication_enabled: bool
    registration_enabled: bool
    password_reset_enabled: bool
    service: AuthService | None
    database_v2_profile_source: bool = False


def _resolve_web_auth_backend(settings: Settings) -> str:
    backend = settings.storage_backend.strip().lower()
    postgres_selected = backend in {"postgres", "postgresql"}
    mysql_v2_selected = settings.database_v2_enabled
    postgres_ready = postgres_selected and postgres_is_configured(settings)
    mysql_v2_ready = mysql_v2_selected and all(
        (settings.mysql_database, settings.mysql_user, settings.mysql_password)
    )
    if settings.public_web_auth_enabled:
        if postgres_selected and not postgres_ready:
            raise RuntimeError(
                "PUBLIC_WEB_AUTH_ENABLED=true with STORAGE_BACKEND=postgresql requires "
                "complete POSTGRES_DATABASE/POSTGRES_USER/POSTGRES_PASSWORD settings"
            )
        if mysql_v2_selected and not mysql_v2_ready:
            raise RuntimeError(
                "PUBLIC_WEB_AUTH_ENABLED=true with DATABASE_V2_ENABLED=true requires "
                "complete MYSQL_DATABASE/MYSQL_USER/MYSQL_PASSWORD settings"
            )
        if not postgres_selected and not mysql_v2_selected:
            raise RuntimeError(
                "PUBLIC_WEB_AUTH_ENABLED=true requires one web auth primary store: "
                "set STORAGE_BACKEND=postgresql or DATABASE_V2_ENABLED=true"
            )
    # Both stores may run together: PostgreSQL owns chat history/memories while
    # Database V2 (MySQL) owns web accounts and profiles. When both are ready the
    # web auth primary store is deterministically mysql_v2 (the identity layer).
    if mysql_v2_ready:
        return "mysql_v2"
    if postgres_ready:
        return "postgres"
    return "none"


def configure_public_web_auth(app: FastAPI, settings: Settings) -> PublicWebAuthRuntime:
    backend = _resolve_web_auth_backend(settings)
    repository = None
    database_v2_profile_source = False
    if backend == "postgres":
        repository = PostgreSQLAuthRepository(settings)
    elif backend == "mysql_v2":
        repository = MySQLAuthRepository(settings)
        database_v2_profile_source = True

    if not settings.public_web_auth_enabled or repository is None:
        return PublicWebAuthRuntime(False, False, False, None)

    service = AuthService(
        repository,
        session_lifetime=timedelta(seconds=settings.public_web_session_lifetime_seconds),
        audit_sink=repository,
    )
    app.include_router(
        create_auth_router(
            service,
            session_cookie_secure=settings.session_cookie_secure,
            login_rate_limiter=AuthRateLimitService(repository),
        )
    )

    registration_enabled = bool(
        settings.email_delivery_enabled
        and all(
            (
                settings.smtp_host,
                settings.smtp_username,
                settings.smtp_password,
                settings.smtp_from_address,
            )
        )
    )
    if not registration_enabled:
        return PublicWebAuthRuntime(
            True,
            False,
            False,
            service,
            database_v2_profile_source=database_v2_profile_source,
        )

    delivery = SmtpEmailVerificationDelivery(
        SmtpEmailSettings(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_address=settings.smtp_from_address,
            starttls=settings.smtp_starttls,
        )
    )
    app.include_router(
        create_registration_router(
            RegistrationService(repository),
            delivery,
            AuthRateLimitService(repository),
            verify_rate_limiter=AuthRateLimitService(repository, limit=30),
        )
    )
    app.include_router(
        create_password_reset_router(
            PasswordResetService(repository, delivery, audit_sink=repository),
            AuthRateLimitService(repository),
            confirm_rate_limiter=AuthRateLimitService(repository, limit=30),
        )
    )
    return PublicWebAuthRuntime(
        True,
        True,
        True,
        service,
        database_v2_profile_source=database_v2_profile_source,
    )
