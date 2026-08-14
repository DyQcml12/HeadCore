from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.password_reset import PasswordResetError, PasswordResetService
from app.auth.rate_limit import AuthRateLimitService, RateLimitError


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


class PasswordResetConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=512)


class PasswordResetRequestAcceptedResponse(BaseModel):
    status: str = "request_accepted"


class PasswordResetCompletedResponse(BaseModel):
    status: str = "password_updated"


def create_password_reset_router(
    service: PasswordResetService,
    rate_limiter: AuthRateLimitService | None = None,
    confirm_rate_limiter: AuthRateLimitService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post(
        "/password-reset/request",
        response_model=PasswordResetRequestAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def request_password_reset(
        request: PasswordResetRequest,
    ) -> PasswordResetRequestAcceptedResponse:
        try:
            if rate_limiter is not None:
                await rate_limiter.enforce(subject_kind="email", subject=request.email)
            await service.request(email=request.email)
        except RateLimitError as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="try again later") from exc
        return PasswordResetRequestAcceptedResponse()

    @router.post("/password-reset/confirm", response_model=PasswordResetCompletedResponse)
    async def confirm_password_reset(
        request: PasswordResetConfirmation,
    ) -> PasswordResetCompletedResponse:
        try:
            if confirm_rate_limiter is not None:
                await confirm_rate_limiter.enforce(subject_kind="password_reset_code", subject="global")
            await service.confirm(token=request.token, password=request.password)
        except RateLimitError as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="try again later") from exc
        except PasswordResetError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return PasswordResetCompletedResponse()

    return router
