from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.email_delivery import EmailVerificationDelivery
from app.auth.registration import RegistrationError, RegistrationService
from app.auth.rate_limit import AuthRateLimitService, RateLimitError


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class EmailVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=256)


class VerificationPendingResponse(BaseModel):
    status: str = "verification_pending"


class VerifiedResponse(BaseModel):
    status: str = "verified"


def create_registration_router(
    service: RegistrationService,
    delivery: EmailVerificationDelivery,
    rate_limiter: AuthRateLimitService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.post("/register", response_model=VerificationPendingResponse, status_code=status.HTTP_202_ACCEPTED)
    async def register(request: RegistrationRequest) -> VerificationPendingResponse:
        try:
            if rate_limiter is not None:
                await rate_limiter.enforce(subject_kind="email", subject=request.email)
            result = await service.register(
                email=request.email,
                display_name=request.display_name,
                password=request.password,
            )
            await delivery.send_verification(
                email=result.email_normalized,
                token=result.verification_token,
                expires_at=result.verification_expires_at,
            )
        except RegistrationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        except RateLimitError as exc:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="try again later") from exc
        return VerificationPendingResponse()

    @router.post("/verify-email", response_model=VerifiedResponse)
    async def verify_email(request: EmailVerificationRequest) -> VerifiedResponse:
        try:
            await service.verify_email(token=request.token)
        except RegistrationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return VerifiedResponse()

    return router
