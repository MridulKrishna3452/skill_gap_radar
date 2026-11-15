"""Request ID, access logging and security headers, as pure ASGI middleware."""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_body
from app.core.logging import request_id_ctx

logger = logging.getLogger("app.access")

REQUEST_ID_HEADER = "x-request-id"
# Accept a caller-supplied ID only if it is short and plain, so it is safe to log and echo.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if self.hsts:
                    headers.setdefault(
                        "strict-transport-security", "max-age=63072000; includeSubDomains"
                    )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Unhandled errors are answered here rather than by Starlette's outer
            # ServerErrorMiddleware, so the 500 still carries the request ID and the
            # security headers, and never exposes the exception text.
            logger.exception("Unhandled error")
            if response_started:
                raise
            body = error_body("internal_error", "An unexpected error occurred")
            response = JSONResponse(body, status_code=500)
            await response(scope, receive, send_wrapper)
        finally:
            # Path only (no query string), so tokens or PII in query params are never logged.
            logger.info(
                "%s %s %s %.1fms",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - started) * 1000,
            )
            request_id_ctx.reset(token)
