"""
Structured logging for the JobCrawler API.

Development : human-readable coloured output to stdout.
Production  : one JSON object per line to stdout — compatible with
              Google Cloud Logging, Datadog, Loki, and any log aggregator
              that ingests structured JSON.

Usage
-----
At application start (once)::

    from api.logger import setup_logging
    setup_logging(app_env="production", debug=False)

In any module::

    from api.logger import get_logger
    log = get_logger(__name__)   # → crawler.<leaf_module>

Adding structured fields to a single log line::

    log.info("application tracked", extra={"user_id": uid, "app_id": app_id})
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# ── request-scoped context ────────────────────────────────────────────────────

# Set by RequestLoggingMiddleware; read by JsonFormatter to correlate log lines.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

# ── formatters ────────────────────────────────────────────────────────────────

# All built-in LogRecord attributes — skip these when collecting extra fields so
# we don't double-emit internal state.
_RECORD_BUILTINS = frozenset({
    "args", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs",
    "msg", "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "thread", "threadName", "taskName",
})


class JsonFormatter(logging.Formatter):
    """Emit one compact JSON object per log record.

    Always-present keys: ``ts``, ``level``, ``logger``, ``msg``, ``request_id``.
    Any ``extra`` kwargs passed to the log call are merged at the top level.
    """

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict[str, Any] = {
            "ts": (
                datetime.fromtimestamp(record.created, tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
            "request_id": request_id_var.get(),
        }

        # Merge caller-supplied extra fields (e.g. user_id, status, duration_ms)
        for key, value in record.__dict__.items():
            if key not in _RECORD_BUILTINS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)


_RESET = "\033[0m"
_LEVEL_COLORS = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}


class ColourFormatter(logging.Formatter):
    """Compact, coloured single-line format for local development."""

    _FMT   = "%(asctime)s  %(levelname)-8s  %(name)-24s  %(message)s"
    _DATEFMT = "%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        colour = _LEVEL_COLORS.get(record.levelname, "")
        fmt = logging.Formatter(
            f"{colour}{self._FMT}{_RESET}", datefmt=self._DATEFMT
        )
        return fmt.format(record)


# ── noisy third-party loggers silenced at WARNING ─────────────────────────────

_QUIET = [
    "urllib3", "httpx", "httpcore", "asyncio",
    "uvicorn.access",            # request logs come from our own middleware
    "uvicorn.error",             # keep only ERROR+ from uvicorn internals
    "sqlalchemy.engine",
    "passlib",
]

# ── setup (called once) ───────────────────────────────────────────────────────

_configured = False


def setup_logging(app_env: str = "development", debug: bool = False) -> None:
    """Configure the root logger.  Call once at application startup.

    Parameters
    ----------
    app_env:
        ``"production"`` → JSON formatter; everything else → colour formatter.
    debug:
        When ``True``, root level is set to ``DEBUG``; otherwise ``INFO``.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Remove any handlers added by uvicorn / import-time basicConfig calls
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if debug else logging.INFO)
    handler.setFormatter(
        JsonFormatter() if app_env == "production" else ColourFormatter()
    )
    root.addHandler(handler)

    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)


# ── factory ───────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """Return a ``crawler.<leaf>`` logger.

    Works with either a dotted module path or a bare name::

        get_logger(__name__)          # api.services.scorer  → crawler.scorer
        get_logger("crawler.scorer")  # crawler.scorer       → crawler.scorer
        get_logger("http")            # http                 → crawler.http
    """
    leaf = name.rsplit(".", 1)[-1]
    return logging.getLogger(f"crawler.{leaf}")
