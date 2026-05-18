"""
Structured error envelope and exception types for tradingview-mcp.

All recoverable failures return a typed error envelope:

    {"error": {"code": "<CODE>", "message": "<human-readable>", **extras}}

Use :func:`make_error` to construct envelopes and :func:`is_error` to check
them. Service layers may also raise typed exceptions (e.g.
:class:`BatchExecutionError`) which the MCP tool wrapper layer converts to the
same envelope shape so MCP clients see a uniform error API.

Migration notes
---------------
- Tools that adopt this format return ``dict`` (the envelope) on error and
  their normal type on success — the static return type becomes a union.
- Callers must check ``isinstance(result, dict) and "error" in result``
  instead of substring-matching previous ``{"error": "Analysis failed: ..."}``
  strings.
- Adoption is opt-in per tool; see PR notes for the current opt-in set.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Union


class ErrorCode(str, Enum):
    """Stable string codes for programmatic branching by MCP clients.

    Values are plain strings so they survive JSON serialization without
    extra encoding, and so they can be compared against literals like
    ``code == "ALL_BATCHES_FAILED"`` from any language.
    """

    # Input / validation
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    INVALID_EXCHANGE = "INVALID_EXCHANGE"
    INVALID_TIMEFRAME = "INVALID_TIMEFRAME"
    INVALID_PARAMETER = "INVALID_PARAMETER"

    # Upstream (TradingView / Yahoo / RSS feeds)
    UPSTREAM_RATE_LIMIT = "UPSTREAM_RATE_LIMIT"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    ALL_BATCHES_FAILED = "ALL_BATCHES_FAILED"

    # Data
    NO_DATA = "NO_DATA"
    PARTIAL_DATA = "PARTIAL_DATA"

    # Environment
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    INTERNAL_ERROR = "INTERNAL_ERROR"


def make_error(code: Union[ErrorCode, str], message: str, **extra: Any) -> dict[str, Any]:
    """Construct a structured error envelope.

    Args:
        code: An :class:`ErrorCode` value or its raw string form. Accepting
            plain strings keeps the helper usable from code that doesn't want
            to import the enum (and from external contributions adopting the
            envelope shape).
        message: Human-readable description suitable for showing to a user.
        **extra: Additional structured fields — e.g. ``retry_after_s=30``,
            ``batches_attempted=5``, ``first_error="..."``, ``symbol="AAPL"``.

    Returns:
        ``{"error": {"code": ..., "message": ..., **extra}}``
    """
    code_str = code.value if isinstance(code, ErrorCode) else str(code)
    err: dict[str, Any] = {"code": code_str, "message": message}
    if extra:
        err.update(extra)
    return {"error": err}


def is_error(payload: Any) -> bool:
    """True if *payload* is an error envelope produced by :func:`make_error`.

    Checks both the outer ``"error"`` key and the inner ``"code"`` to avoid
    false positives against legacy string-error payloads (which had
    ``payload["error"]`` as a string, not a dict).
    """
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("error"), dict)
        and "code" in payload["error"]
    )


class BatchExecutionError(Exception):
    """Raised by batched scanners when every batch failed.

    The service layer raises this so the MCP tool wrapper at the boundary
    can convert it to an :func:`make_error` envelope with full context.
    Callers must not swallow it silently — that defeats the whole point of
    the sentinel.

    Attributes:
        batches_attempted: How many batches were issued to upstream.
        batches_failed: How many of those failed
            (equals ``batches_attempted`` whenever this is raised).
        first_error: ``repr()`` of the first exception observed across the
            batch loop, kept verbatim for debugging.
    """

    def __init__(
        self,
        batches_attempted: int,
        batches_failed: int,
        first_error: str,
    ) -> None:
        super().__init__(
            f"All {batches_attempted} batches failed; first error: {first_error}"
        )
        self.batches_attempted = batches_attempted
        self.batches_failed = batches_failed
        self.first_error = first_error
