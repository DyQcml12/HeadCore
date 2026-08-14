from __future__ import annotations

from dataclasses import dataclass

from app.auth.service import AuthService, AuthenticationError


class AuthenticationRequiredError(Exception):
    pass


class CsrfValidationError(Exception):
    pass


@dataclass(frozen=True)
class WebIdentity:
    profile_id: str
    session_id: str


def bearer_session_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        return None
    return token.strip()


async def resolve_web_identity(
    *,
    auth_service: AuthService | None,
    public_auth_enabled: bool,
    session_token: str | None,
    csrf_token: str | None = None,
    require_csrf: bool = False,
    supplied_user_id: str,
    supplied_session_id: str,
) -> WebIdentity:
    if not public_auth_enabled:
        return WebIdentity(profile_id=supplied_user_id, session_id=supplied_session_id)
    if auth_service is None:
        raise AuthenticationRequiredError("authentication required")
    try:
        session = await auth_service.require_session(
            session_token=session_token,
            csrf_token=csrf_token,
            require_csrf=require_csrf,
        )
    except AuthenticationError as exc:
        if require_csrf and str(exc) == "csrf validation failed":
            raise CsrfValidationError("csrf validation failed") from exc
        raise AuthenticationRequiredError("authentication required") from exc
    return WebIdentity(profile_id=session.profile_id, session_id=session.id)
