"""Logging setup: JSON lines in production, readable text in development.

Every record carries the current request ID (set by RequestIDMiddleware) so a client-facing
error can be traced to its log lines.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


# Credentials that must never reach a log line, whatever logs them (our code, a library, an
# exception message). Applied to the fully formatted line, including tracebacks.
_REDACTIONS = [
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)(sr_refresh=)[^;\s,]+"), r"\1[REDACTED]"),
    (
        re.compile(
            r"(?i)([\"']?\b(?:\w*password|app_key|api_key|\w*secret|\w*token)[\"']?\s*[:=]\s*)"
            r"([\"']?)[^\s\"',;&}]+"
        ),
        r"\1\2[REDACTED]",
    ),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, ensure_ascii=False))


def configure_logging(level: str, *, json_output: bool) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIDFilter())
    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            RedactingFormatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn's access log duplicates our request logging and would log raw query strings.
    logging.getLogger("uvicorn.access").disabled = True
    # httpx logs every request URL at INFO. Adzuna takes its API key as a query parameter,
    # so those lines would leak the key into logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
