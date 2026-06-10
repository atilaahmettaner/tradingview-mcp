"""Unit tests for ``core/logging_config.py`` (P5).

Locks in the contract the rest of the server relies on:
- logs go to **stderr**, never stdout (stdout is the stdio JSON-RPC channel);
- ``LOG_LEVEL`` is honored, ``DEBUG_MCP`` forces DEBUG, bad values fall back;
- configuration is idempotent (no duplicate handlers on repeat calls);
- ``LOG_FORMAT=json`` emits parseable JSON;
- ``LOG_FILE`` adds a rotating file handler.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys

import pytest

from tradingview_mcp.core import logging_config as lc


@pytest.fixture(autouse=True)
def _isolate_logger():
    """Snapshot and restore the package logger + module state so each test
    starts from a clean slate and leaves no handlers behind."""
    logger = logging.getLogger(lc.ROOT_LOGGER_NAME)
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    saved_configured = lc._CONFIGURED

    for h in list(logger.handlers):
        logger.removeHandler(h)
    lc._CONFIGURED = False

    yield logger

    for h in list(logger.handlers):
        logger.removeHandler(h)
    for h in saved_handlers:
        logger.addHandler(h)
    logger.setLevel(saved_level)
    lc._CONFIGURED = saved_configured


def test_returns_package_logger():
    logger = lc.configure_logging(force=True)
    assert logger.name == lc.ROOT_LOGGER_NAME


def test_default_level_is_warning(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DEBUG_MCP", raising=False)
    logger = lc.configure_logging(force=True)
    assert logger.level == logging.WARNING


def test_log_level_env_honored(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    logger = lc.configure_logging(force=True)
    assert logger.level == logging.DEBUG


def test_invalid_log_level_falls_back_to_warning(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "NOPE")
    logger = lc.configure_logging(force=True)
    assert logger.level == logging.WARNING


def test_debug_mcp_forces_debug(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "ERROR")  # DEBUG_MCP must override
    monkeypatch.setenv("DEBUG_MCP", "1")
    logger = lc.configure_logging(force=True)
    assert logger.level == logging.DEBUG


def test_handler_writes_to_stderr_not_stdout(monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    logger = lc.configure_logging(force=True)
    streams = [getattr(h, "stream", None) for h in logger.handlers]
    assert sys.stderr in streams
    assert sys.stdout not in streams


def test_idempotent_no_duplicate_handlers():
    logger = lc.configure_logging(force=True)
    n = len(logger.handlers)
    lc.configure_logging()          # no force: should be a no-op
    lc.configure_logging(force=True)  # force: re-reads but must not stack
    assert len(logger.handlers) == n


def test_json_format_emits_parseable_json(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    logger = lc.configure_logging(force=True)
    handler = logger.handlers[0]
    assert isinstance(handler.formatter, lc.JsonFormatter)

    record = logger.makeRecord(
        logger.name, logging.WARNING, __file__, 1, "hello %s", ("world",), None
    )
    line = handler.formatter.format(record)
    payload = json.loads(line)
    assert payload["level"] == "WARNING"
    assert payload["logger"] == lc.ROOT_LOGGER_NAME
    assert payload["msg"] == "hello world"


def test_log_file_adds_rotating_handler(monkeypatch, tmp_path):
    log_file = tmp_path / "server.log"
    monkeypatch.setenv("LOG_FILE", str(log_file))
    logger = lc.configure_logging(force=True)

    file_handlers = [
        h for h in logger.handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1

    logger.warning("written to file")
    for h in logger.handlers:
        h.flush()
    assert log_file.exists()
    assert "written to file" in log_file.read_text()
