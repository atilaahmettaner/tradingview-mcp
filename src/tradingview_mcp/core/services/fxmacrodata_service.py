"""FXMacroData release-calendar service helpers."""

from __future__ import annotations

import os
import re
from typing import Any, Optional

import httpx

from tradingview_mcp.core.errors import ErrorCode, make_error

FXMACRODATA_BASE_URL = "https://api.fxmacrodata.com/v1"

_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")


def _parse_tier(value: Any) -> Optional[int]:
    """Parse a ``market_tier`` value, returning None for anything non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _retry_after_s(response: httpx.Response) -> Optional[int]:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _http_error_envelope(exc: httpx.HTTPError, currency: str) -> dict[str, Any]:
    """Translate an httpx failure into the structured error envelope."""
    if isinstance(exc, httpx.TimeoutException):
        return make_error(
            ErrorCode.UPSTREAM_TIMEOUT,
            "FXMacroData release calendar request timed out",
            currency=currency,
            retryable=True,
        )

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            extra: dict[str, Any] = {}
            retry_after = _retry_after_s(exc.response)
            if retry_after is not None:
                extra["retry_after_s"] = retry_after
            return make_error(
                ErrorCode.UPSTREAM_RATE_LIMIT,
                "FXMacroData rate limit reached",
                currency=currency,
                status_code=status,
                retryable=True,
                **extra,
            )
        return make_error(
            ErrorCode.UPSTREAM_ERROR,
            f"FXMacroData returned HTTP {status}",
            currency=currency,
            status_code=status,
            retryable=status >= 500,
        )

    # Connection errors, protocol errors and other transport failures are
    # usually transient.
    return make_error(
        ErrorCode.UPSTREAM_ERROR,
        f"FXMacroData request failed: {exc.__class__.__name__}",
        currency=currency,
        retryable=isinstance(exc, httpx.TransportError),
    )


async def get_release_calendar(
    currency: str = "usd",
    *,
    limit: int = 25,
    min_tier: Optional[int] = None,
    base_url: str = FXMACRODATA_BASE_URL,
) -> dict[str, Any]:
    """Fetch FXMacroData official-source release-calendar events.

    Returns the calendar payload on success, or a structured error envelope
    (see :mod:`tradingview_mcp.core.errors`) on invalid input or upstream
    failure.
    """

    if not isinstance(currency, str) or not _CURRENCY_RE.match(currency):
        return make_error(
            ErrorCode.INVALID_PARAMETER,
            f"currency must be a 3-letter ISO code (e.g. usd, eur), got {currency!r}",
            parameter="currency",
            retryable=False,
        )
    currency = currency.lower()

    limit_count = max(1, min(int(limit), 100))
    params: dict[str, str] = {"limit": str(limit_count)}
    headers: dict[str, str] = {}
    api_key = os.getenv("FXMACRODATA_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    url = f"{base_url.rstrip('/')}/calendar/{currency}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return _http_error_envelope(exc, currency)

    try:
        payload = response.json()
    except ValueError:
        return make_error(
            ErrorCode.UPSTREAM_ERROR,
            "FXMacroData returned a non-JSON response",
            currency=currency,
            retryable=True,
        )
    events = (payload.get("data") or []) if isinstance(payload, dict) else None
    if not isinstance(events, list) or (
        "detail" in payload and "data" not in payload
    ):
        return make_error(
            ErrorCode.UPSTREAM_ERROR,
            "FXMacroData returned an unexpected response shape",
            currency=currency,
            retryable=False,
        )

    if min_tier is not None:
        filtered = []
        for event in events:
            if not isinstance(event, dict):
                continue
            tier = _parse_tier(event.get("market_tier"))
            # Events with a missing or non-numeric tier are treated as lowest
            # priority, so any tier filter excludes them.
            if tier is not None and tier <= min_tier:
                filtered.append(event)
        events = filtered

    events = events[:limit_count]
    return {
        "currency": payload.get("currency", currency.upper()),
        "timezone": payload.get("timezone"),
        "data_quality": payload.get("data_quality"),
        "events": events,
    }
