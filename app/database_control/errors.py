from __future__ import annotations


class DatabaseControlError(Exception):
    code = "database_control_error"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def response(self) -> dict[str, dict[str, str]]:
        return {"error": {"code": self.code, "message": self.message}}


class UnauthenticatedError(DatabaseControlError):
    code = "unauthenticated"
    status_code = 401


class ForbiddenError(DatabaseControlError):
    code = "admin_required"
    status_code = 403


class ResourceNotFoundError(DatabaseControlError):
    code = "not_found"
    status_code = 404


class ResourceConflictError(DatabaseControlError):
    code = "conflict"
    status_code = 409


class DatabaseNotReadyError(DatabaseControlError):
    code = "database_not_ready"
    status_code = 503


class DatabaseUnavailableError(DatabaseControlError):
    code = "database_unavailable"
    status_code = 503


def translate_database_exception(exc: Exception) -> DatabaseControlError | None:
    module = type(exc).__module__.lower()
    name = type(exc).__name__.lower()
    if "integrity" in name or "constraint" in name or "duplicate" in name:
        return ResourceConflictError("database constraint conflict")
    if (
        module.startswith("asyncmy")
        or "operational" in name
        or "interface" in name
        or isinstance(exc, (ConnectionError, TimeoutError, OSError))
    ):
        return DatabaseUnavailableError("Database V2 is temporarily unavailable")
    return None
