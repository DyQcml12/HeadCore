from __future__ import annotations

from enum import StrEnum


class WorldSourceErrorCode(StrEnum):
    SOURCE_NOT_FOUND = "source_not_found"
    SOURCE_DISABLED = "source_disabled"
    CAPABILITY_UNSUPPORTED = "capability_unsupported"
    POLICY_DENIED = "policy_denied"
    CONSENT_REQUIRED = "consent_required"
    NOT_CONFIGURED = "not_configured"
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    RESPONSE_TOO_LARGE = "response_too_large"
    INVALID_RESPONSE = "invalid_response"
    UNAVAILABLE = "unavailable"


class WorldSourceError(RuntimeError):
    def __init__(
        self,
        code: WorldSourceErrorCode,
        message: str = "",
        *,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message or code.value)
        self.code = code
        self.retryable = (
            code
            in {
                WorldSourceErrorCode.RATE_LIMITED,
                WorldSourceErrorCode.TIMEOUT,
                WorldSourceErrorCode.UNAVAILABLE,
            }
            if retryable is None
            else retryable
        )
