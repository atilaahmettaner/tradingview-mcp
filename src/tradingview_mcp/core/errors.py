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


class ScreenerServiceError(RuntimeError):
    """Typed service-layer failure carrying an :class:`ErrorCode`.

    Subclasses ``RuntimeError`` deliberately: the pre-envelope service guards
    raised bare ``RuntimeError``, so any external caller with
    ``except RuntimeError`` keeps working unchanged while the MCP boundary
    gains a lossless translation to the structured envelope.

    Attributes:
        code:  Stable :class:`ErrorCode` for programmatic branching.
        extra: Structured context merged into the envelope
               (e.g. ``exchange="EGX"``, ``retryable=True``).
    """

    def __init__(self, code: Union[ErrorCode, str], message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.extra = extra

    def to_envelope(self) -> dict[str, Any]:
        return make_error(self.code, str(self), **self.extra)


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


class PartialDataError(Exception):
    """Raised when a batched scan aborted early but still produced rows.

    Wall-clock budgets and consecutive-failure bails used to return a plain
    truncated list, indistinguishable from a complete scan — the abort reason
    went only to stderr. This carries the partial rows plus scan telemetry so
    the MCP boundary can return them WITH a PARTIAL_DATA envelope.

    Attributes:
        rows: The rows collected before the abort (already sorted/truncated).
        batches_attempted / total_batches: Scan progress at abort time.
        aborted_reason: Human-readable cause ("wall-clock budget…", …).
    """

    def __init__(
        self,
        rows: list,
        batches_attempted: int,
        total_batches: int,
        aborted_reason: str,
    ) -> None:
        super().__init__(
            f"Partial scan: {batches_attempted}/{total_batches} batches before abort "
            f"({aborted_reason})"
        )
        self.rows = rows
        self.batches_attempted = batches_attempted
        self.total_batches = total_batches
        self.aborted_reason = aborted_reason


def exception_to_envelope(exc: BaseException, *, context: str = "") -> dict[str, Any]:
    """Translate any exception into the structured envelope at the MCP boundary.

    ``retryable`` semantics: batched-scan wipeouts are storms that pass, so
    they are marked retryable; unexpected exceptions are not (retrying the
    same bug yields the same crash).

    Args:
        exc:     The caught exception.
        context: Tool name prefixed to unexpected-exception messages so the
                 envelope stays diagnosable without a traceback.
    """
    if isinstance(exc, ScreenerServiceError):
        return exc.to_envelope()
    if isinstance(exc, PartialDataError):
        env = make_error(
            ErrorCode.PARTIAL_DATA, str(exc),
            batches_attempted=exc.batches_attempted,
            total_batches=exc.total_batches,
            aborted_reason=exc.aborted_reason,
            retryable=True,
        )
        # Partial rows ride alongside the error so callers keep the data.
        env["rows"] = exc.rows
        return env
    if isinstance(exc, BatchExecutionError):
        return make_error(
            ErrorCode.ALL_BATCHES_FAILED, str(exc),
            batches_attempted=exc.batches_attempted,
            batches_failed=exc.batches_failed,
            first_error=exc.first_error,
            retryable=True,
        )
    msg = f"{context} failed: {exc!r}" if context else repr(exc)
    return make_error(ErrorCode.INTERNAL_ERROR, msg, retryable=False)
