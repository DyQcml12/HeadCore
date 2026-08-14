from __future__ import annotations

from fastapi import APIRouter, Cookie, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.identity import bearer_session_token
from app.auth.service import AuthService, AuthenticationError
from app.auth.rate_limit import AuthRateLimitService, RateLimitError


SESSION_COOKIE_NAME = "hutao_session"
CSRF_COOKIE_NAME = "hutao_csrf"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class LoginResponse(BaseModel):
    profile_id: str
    expires_at: str
    csrf_token: str


class MobileLoginResponse(LoginResponse):
    access_token: str


class CurrentAccountResponse(BaseModel):
    profile_id: str
    display_name: str
    email: str
    email_verified: bool
    created_at: str
    session_expires_at: str


def create_auth_router(
    service: AuthService,
    *,
    session_cookie_secure: bool = False,
    login_rate_limiter: AuthRateLimitService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/login", response_model=LoginResponse)
    async def login(request: LoginRequest, response: Response) -> LoginResponse:
        try:
            if login_rate_limiter is not None:
                await login_rate_limiter.enforce(subject_kind="email", subject=request.email)
            authenticated = await service.login(email=request.email, password=request.password)
        except RateLimitError as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="try again later") from exc
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid email or password",
            ) from exc
        max_age = max(1, int((authenticated.expires_at.timestamp() - _utc_timestamp())))
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=authenticated.session_token,
            max_age=max_age,
            httponly=True,
            secure=session_cookie_secure,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=authenticated.csrf_token,
            max_age=max_age,
            httponly=False,
            secure=session_cookie_secure,
            samesite="lax",
            path="/",
        )
        return LoginResponse(
            profile_id=authenticated.profile_id,
            expires_at=authenticated.expires_at.isoformat(),
            csrf_token=authenticated.csrf_token,
        )

    @router.post("/mobile/login", response_model=MobileLoginResponse)
    async def mobile_login(request: LoginRequest) -> MobileLoginResponse:
        try:
            if login_rate_limiter is not None:
                await login_rate_limiter.enforce(subject_kind="email", subject=request.email)
            authenticated = await service.login(email=request.email, password=request.password)
        except RateLimitError as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="try again later") from exc
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid email or password",
            ) from exc
        return MobileLoginResponse(
            profile_id=authenticated.profile_id,
            expires_at=authenticated.expires_at.isoformat(),
            csrf_token=authenticated.csrf_token,
            access_token=authenticated.session_token,
        )

    @router.get("/me", response_model=CurrentAccountResponse)
    async def current_account(
        hutao_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        authorization: str | None = Header(default=None),
    ) -> CurrentAccountResponse:
        try:
            authenticated = await service.current_account(
                session_token=bearer_session_token(authorization) or hutao_session
            )
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            ) from exc
        profile = authenticated.profile
        return CurrentAccountResponse(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            email=profile.email_normalized,
            email_verified=profile.email_verified,
            created_at=profile.created_at.isoformat(),
            session_expires_at=authenticated.session_expires_at.isoformat(),
        )

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        response: Response,
        hutao_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        authorization: str | None = Header(default=None),
    ) -> Response:
        try:
            await service.require_session(
                session_token=bearer_session_token(authorization) or hutao_session,
                csrf_token=csrf_token,
                require_csrf=True,
            )
            await service.logout(session_token=bearer_session_token(authorization) or hutao_session)
        except AuthenticationError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    return router


def _utc_timestamp() -> float:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).timestamp()

