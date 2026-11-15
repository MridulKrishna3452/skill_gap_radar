"""One error shape for every failure: {"error": {"code", "message", "request_id", "details"?}}.

Unexpected exceptions are logged with their traceback but the client only gets a generic
message, so internals (SQL, file paths, stack traces) never leak. That last case is handled in
RequestContextMiddleware, which sits inside Starlette's outermost error middleware.
"""

from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx


class AppError(Exception):
    """Base class for expected, client-facing errors raised by services."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id_ctx.get()}
    if details is not None:
        error["details"] = details
    return {"error": error}


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    err = cast(AppError, exc)
    return JSONResponse(error_body(err.code, err.message, err.details), err.status_code)


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    err = cast(StarletteHTTPException, exc)
    try:
        code = HTTPStatus(err.status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        code = "http_error"
    return JSONResponse(error_body(code, str(err.detail)), err.status_code, headers=err.headers)


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    err = cast(RequestValidationError, exc)
    # Drop the echoed "input" so uploaded or sensitive values are not reflected back.
    details = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
        for e in err.errors()
    ]
    return JSONResponse(error_body("validation_error", "Request validation failed", details), 422)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    # Unhandled exceptions are answered by RequestContextMiddleware (see middleware.py).
