"""Central logging configuration for the TradingView MCP server.

Server and service code log through the ``tradingview_mcp`` logger hierarchy
(every module does ``logger = logging.getLogger(__name__)``).
``configure_logging()`` is called once from ``server.main()`` to attach a
handler, set the level, and choose a format.

CRITICAL: every handler writes to **stderr**, never stdout. Under the stdio
transport, stdout *is* the JSON-RPC channel — a stray byte there corrupts the
MCP protocol stream. stderr is free for operator/diagnostic logs.

Env vars (all optional):
  LOG_LEVEL          DEBUG | INFO | WARNING | ERROR | CRITICAL  (default WARNING)
  LOG_FORMAT         "plain" (default) | "json"
  LOG_FILE           path; if set, ALSO write to a size-rotated file
  LOG_FILE_MAX_BYTES per-file cap before rotation (default 5_000_000)
  LOG_FILE_BACKUPS   number of rotated files to keep (default 3)
  DEBUG_MCP          if set to any value, forces level to DEBUG

The default level is WARNING so the transient-error / batch-failure messages
the server already emitted to stderr stay visible; INFO/DEBUG (entry traces,
retry/cooldown detail) are opt-in via ``LOG_LEVEL``.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys

ROOT_LOGGER_NAME = "tradingview_mcp"
_DEFAULT_LEVEL = "WARNING"
_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Minimal structured formatter — one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _resolve_level() -> int:
    if os.environ.get("DEBUG_MCP"):
        return logging.DEBUG
    raw = os.environ.get("LOG_LEVEL", _DEFAULT_LEVEL).upper()
    level = getattr(logging, raw, None)
    return level if isinstance(level, int) else logging.WARNING


def _build_formatter() -> logging.Formatter:
    if os.environ.get("LOG_FORMAT", "plain").lower() == "json":
        return JsonFormatter()
    return logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def configure_logging(*, force: bool = False) -> logging.Logger:
    """Configure the ``tradingview_mcp`` logger. Idempotent.

    Returns the configured package logger. Pass ``force=True`` (used by tests)
    to re-read the environment after monkeypatching it.

    ``propagate`` is left at its default (True): in production the root logger
    has no handlers, so records emit exactly once through our handler; under
    pytest, propagation lets ``caplog`` capture them.
    """
    global _CONFIGURED
    logger = logging.getLogger(ROOT_LOGGER_NAME)

    if _CONFIGURED and not force:
        return logger

    # Remove handlers we previously attached so re-config never duplicates.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    logger.setLevel(_resolve_level())
    formatter = _build_formatter()

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    log_file = os.environ.get("LOG_FILE")
    if log_file:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=int(os.environ.get("LOG_FILE_MAX_BYTES", "5000000")),
                backupCount=int(os.environ.get("LOG_FILE_BACKUPS", "3")),
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            logger.warning("could not open LOG_FILE=%r; file logging disabled", log_file, exc_info=True)

    _CONFIGURED = True
    return logger
