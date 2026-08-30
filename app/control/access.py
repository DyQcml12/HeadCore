from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.identity import bearer_session_token
from app.auth.service import AuthService, AuthenticationError, AuthenticatedAccount
from app.database_control.contracts import (
    DatabaseActor,
    DatabasePermissions,
    SourceAccount,
)
from app.operations.control_write import ControlWriteGuard


SESSION_COOKIE_NAME = "hutao_session"
CSRF_HEADER_NAME = "X-CSRF-Token"


@dataclass(frozen=True)
class ControlWebRuntime:
    """Web identity boundary for the local control plane.

    The message-channel actor resolver remains the source of truth for QQ and
    WeChat requests. This runtime only maps an authenticated web account to the
    explicitly configured control-center allowlist.
    """

    enabled: bool = False
    auth_service: AuthService | None = None
    admin_emails: frozenset[str] = frozenset()
    local_only: bool = True


_runtime = ControlWebRuntime()


def configure_control_web_runtime(
    *,
    enabled: bool,
    auth_service: AuthService | None,
    admin_emails: str | frozenset[str] | set[str] = "",
    local_only: bool = True,
) -> None:
    if isinstance(admin_emails, str):
        normalized = frozenset(
            item.strip().lower()
            for item in admin_emails.split(",")
            if item.strip()
        )
    else:
        normalized = frozenset(item.strip().lower() for item in admin_emails if item.strip())
    global _runtime
    _runtime = ControlWebRuntime(
        enabled=bool(enabled),
        auth_service=auth_service,
        admin_emails=normalized,
        local_only=bool(local_only),
    )


def control_web_auth_enabled() -> bool:
    return _runtime.enabled


def _header_value(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    return value.strip() if value and value.strip() else None


def has_internal_actor_headers(request: Request) -> bool:
    return any(
        _header_value(request, name)
        for name in (
            "X-Hutao-Actor-Platform",
            "X-Hutao-Actor-User-Id",
            "X-Hutao-Actor-Group-Id",
        )
    )


def is_loopback_request(request: Request) -> bool:
    client = request.client
    if client is None or not client.host:
        return True
    return client.host.strip().lower() in {"127.0.0.1", "::1", "localhost"}


def require_local_control_scope(request: Request) -> None:
    if _runtime.local_only and not is_loopback_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "control_loopback_only"},
        )


def _synthetic_web_actor(account: AuthenticatedAccount) -> DatabaseActor:
    return DatabaseActor(
        profile_id=account.profile.profile_id,
        relationship_type="admin_partner",
        permissions=DatabasePermissions(read_admin=True, mutate_admin=True),
        source_account=SourceAccount(
            id=f"web-{account.profile.user_id}",
            platform="core",
            status="active",
        ),
    )


async def require_web_admin(
    request: Request,
    *,
    require_csrf: bool = False,
) -> AuthenticatedAccount:
    if not _runtime.enabled or _runtime.auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "control_web_auth_unavailable"},
        )
    session_token = bearer_session_token(request.headers.get("Authorization")) or request.cookies.get(
        SESSION_COOKIE_NAME
    )
    csrf_token = request.headers.get(CSRF_HEADER_NAME)
    try:
        if require_csrf:
            await _runtime.auth_service.require_session(
                session_token=session_token,
                csrf_token=csrf_token,
                require_csrf=True,
            )
        account = await _runtime.auth_service.current_account(session_token=session_token)
    except AuthenticationError as exc:
        if require_csrf and str(exc) == "csrf validation failed":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "csrf_validation_failed"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
        ) from exc
    except Exception as exc:
        # Do not expose storage/driver details through a control endpoint.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "control_auth_unavailable"},
        ) from exc
    if account.profile.email_normalized.lower() not in _runtime.admin_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "control_admin_required"},
        )
    return account


async def authorize_control_request(
    request: Request,
    *,
    operation: str,
    write: bool = False,
    platform: str | None = None,
    user_id: str | None = None,
    group_id: str | None = None,
    control_write_guard: ControlWriteGuard,
) -> DatabaseActor | None:
    """Authorize either an internal actor or an authenticated web admin."""

    require_local_control_scope(request)

    # Explicit actor headers always use the existing database-backed policy.
    # They are never mixed with a browser session to avoid identity confusion.
    if platform or user_id or group_id or has_internal_actor_headers(request):
        if write:
            return await control_write_guard.authorize(
                platform=platform,
                user_id=user_id,
                group_id=group_id,
                operation=operation,
            )
        actor = await control_write_guard.verify(
            platform=platform,
            user_id=user_id,
            group_id=group_id,
        )
        if actor is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "admin_required"})
        return actor

    if not _runtime.enabled:
        # Local-only development keeps the legacy no-auth control surface. The
        # process is still bound to 127.0.0.1 by default; public deployments
        # must enable web auth and provide an allowlist.
        return None

    account = getattr(request.state, "control_web_admin_account", None)
    if account is None:
        account = await require_web_admin(request, require_csrf=write)
        request.state.control_web_admin_account = account
    return _synthetic_web_actor(account)


async def control_access_middleware(request: Request, call_next: Any):
    """Fail closed for every `/api/control/*` route when web auth is enabled."""

    if request.url.path.startswith("/api/control"):
        try:
            require_local_control_scope(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if _runtime.enabled and request.url.path.startswith("/api/control") and not has_internal_actor_headers(request):
        try:
            account = await require_web_admin(
                request,
                require_csrf=request.method.upper() not in {"GET", "HEAD", "OPTIONS"},
            )
            request.state.control_web_admin_account = account
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    response = await call_next(request)
    if request.url.path.startswith("/api/control") or request.url.path.startswith("/control"):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
    return response


async def control_page_response(request: Request, file_response: Any):
    """Return a shell locally, or an authenticated page when public auth is on."""

    require_local_control_scope(request)
    file_response.headers.setdefault("Cache-Control", "no-store")
    file_response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    if not _runtime.enabled:
        return file_response
    try:
        account = await require_web_admin(request)
        request.state.control_web_admin_account = account
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            redirect = RedirectResponse(
                url="/auth?return_to=%2Fcontrol",
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )
            redirect.headers["Cache-Control"] = "no-store"
            redirect.headers["X-Robots-Tag"] = "noindex, nofollow"
            return redirect
        raise
    return file_response
