from __future__ import annotations

import importlib
import importlib.util
from dataclasses import replace

from fastapi import FastAPI

from app.core.config import load_settings


def public_auth_runtime_module():
    spec = importlib.util.find_spec("app.auth.runtime")
    assert spec is not None, "public web auth runtime wiring must be provided"
    return importlib.import_module("app.auth.runtime")


def configured_settings(*, email_delivery_enabled: bool):
    return replace(
        load_settings(),
        public_web_auth_enabled=True,
        database_v2_enabled=True,
        mysql_database="test_hutao",
        mysql_user="test_user",
        mysql_password="test_password",
        email_delivery_enabled=email_delivery_enabled,
        smtp_host="smtp.example.test",
        smtp_username="test_sender",
        smtp_password="test_smtp_password",
        smtp_from_address="noreply@example.test",
    )


def route_paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes}


def test_public_auth_runtime_does_not_mount_registration_or_reset_without_email_delivery() -> None:
    module = public_auth_runtime_module()
    app = FastAPI()

    runtime = module.configure_public_web_auth(
        app,
        configured_settings(email_delivery_enabled=False),
    )

    assert runtime.authentication_enabled is True
    assert runtime.database_v2_profile_source is True
    assert runtime.registration_enabled is False
    assert runtime.password_reset_enabled is False
    assert "/api/v1/auth/login" in route_paths(app)
    assert "/api/v1/auth/register" not in route_paths(app)
    assert "/api/v1/auth/password-reset/request" not in route_paths(app)
    assert "/api/v1/auth/password-reset/confirm" not in route_paths(app)


def test_public_auth_runtime_mounts_registration_and_reset_after_all_dependencies_are_ready() -> None:
    module = public_auth_runtime_module()
    app = FastAPI()

    runtime = module.configure_public_web_auth(
        app,
        configured_settings(email_delivery_enabled=True),
    )

    assert runtime.authentication_enabled is True
    assert runtime.database_v2_profile_source is True
    assert runtime.registration_enabled is True
    assert runtime.password_reset_enabled is True
    assert {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/password-reset/request",
        "/api/v1/auth/password-reset/confirm",
    } <= route_paths(app)
