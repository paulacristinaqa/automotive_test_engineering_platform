from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = structlog.get_logger()


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
    correlation_id: str


class ApplicationError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.headers = headers


class DuplicateEmailError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="email_already_exists",
            message="A user with this email already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )


class DuplicateRoleNameError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="role_name_already_exists",
            message="A role with this name already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )


class DuplicateModuleNameError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="module_name_already_exists",
            message="A module with this name already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )


class ProtectedRoleError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="protected_role",
            message="The protected platform role cannot be changed in this way.",
            status_code=status.HTTP_409_CONFLICT,
        )


class RoleInUseError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="role_in_use",
            message="The role cannot be deleted while it is assigned to users.",
            status_code=status.HTTP_409_CONFLICT,
        )


class ResourceNotFoundError(ApplicationError):
    def __init__(self, resource: str) -> None:
        super().__init__(
            code=f"{resource}_not_found",
            message=f"The requested {resource} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidRefreshTokenError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_refresh_token",
            message="The refresh token is invalid or expired.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class InvalidModuleCredentialError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_module_credential",
            message="The module credential is invalid or has been rotated.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class RateLimitExceededError(ApplicationError):
    def __init__(self, *, limit: int, remaining: int, reset_after: int) -> None:
        headers = {
            "Retry-After": str(reset_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_after),
        }
        super().__init__(
            code="rate_limit_exceeded",
            message="Too many requests. Retry later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"limit": limit, "remaining": remaining, "reset_after": reset_after},
            headers=headers,
        )


class RateLimitUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="rate_limit_unavailable",
            message="Request protection is temporarily unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": "1"},
        )


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", "unavailable"))


def _response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details),
        correlation_id=_correlation_id(request),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        return _response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            code = str(detail.get("code", "http_error"))
            message = str(detail.get("message", "The request could not be completed."))
            details = detail.get("details")
        else:
            code = "http_error"
            message = str(detail)
            details = None
        return _response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": [str(part) for part in error["loc"]],
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return _response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="The request contains invalid data.",
            details=details,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_request_error", error_type=type(exc).__name__)
        return _response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="An unexpected error occurred.",
        )
