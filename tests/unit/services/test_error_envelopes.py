"""Error-envelope contract for the hot single-symbol analysis paths.

Asserts the structured-error rules the MCP guidance calls for:
- SYMBOL_NOT_FOUND: retryable=False + actionable `listed_on` suggestions
  (a valid-but-unlisted symbol must NOT be retried on the same exchange).
- UPSTREAM_ERROR (transient TradingView outage): retryable=True with an
  explicit retry_after_s, so agents wait-and-retry instead of hammering.
- Message prefixes stay backward-compatible ("No data found for",
  "Analysis failed:") for anyone substring-matching the old strings.
"""
import pytest

import tradingview_mcp.core.services.scanner_service as scanner_service
import tradingview_mcp.core.services.screener_service as screener_service
from tradingview_mcp.core.errors import is_error


class _NoIndicators:
    """Truthy analysis row lacking the `indicators` attribute."""


def test_analyze_coin_symbol_not_found_envelope(monkeypatch):
    monkeypatch.setattr(screener_service, "get_multiple_analysis", lambda **kwargs: {})
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)

    out = screener_service.analyze_coin("HYPEUSDT", "BINANCE", "1h")

    assert is_error(out)
    err = out["error"]
    assert err["code"] == "SYMBOL_NOT_FOUND"
    assert err["retryable"] is False
    assert err["message"].startswith("No data found for HYPEUSDT on BINANCE")
    assert "KUCOIN" in err["listed_on"]
    assert "BINANCE" not in err["listed_on"]
    assert err["symbol"] == "HYPEUSDT"
    assert err["timeframe"] == "1h"


def test_analyze_coin_unknown_ticker_says_verify_spelling(monkeypatch):
    monkeypatch.setattr(screener_service, "get_multiple_analysis", lambda **kwargs: {})
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)

    out = screener_service.analyze_coin("ZZZQQQ123XYZ", "BINANCE", "1h")

    err = out["error"]
    assert err["code"] == "SYMBOL_NOT_FOUND"
    assert err["retryable"] is False
    assert err["listed_on"] == []
    assert "verify the ticker" in err["message"].lower()


def test_analyze_coin_upstream_outage_is_retryable(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError(
            "Upstream TradingView scanner returned transient errors on all 3 "
            "attempts spanning 5s (JSONDecodeError('Expecting value: line 1 "
            "column 1 (char 0)'))."
        )

    monkeypatch.setattr(screener_service, "get_multiple_analysis", boom)
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)

    out = screener_service.analyze_coin("BTCUSDT", "BINANCE", "1h")

    assert is_error(out)
    err = out["error"]
    assert err["code"] == "UPSTREAM_ERROR"
    assert err["retryable"] is True
    assert err["retry_after_s"] == 60
    assert err["message"].startswith("Analysis failed:")


def test_volume_confirmation_symbol_not_found_envelope(monkeypatch):
    monkeypatch.setattr(scanner_service, "get_multiple_analysis", lambda **kwargs: {})

    out = scanner_service.volume_confirmation_analyze("HYPEUSDT", "BINANCE", "15m")

    err = out["error"]
    assert err["code"] == "SYMBOL_NOT_FOUND"
    assert err["retryable"] is False
    assert "KUCOIN" in err["listed_on"]
    assert err["full_symbol"] == "BINANCE:HYPEUSDT"


def test_volume_confirmation_no_indicator_row_not_retryable(monkeypatch):
    row = _NoIndicators()
    monkeypatch.setattr(
        scanner_service,
        "get_multiple_analysis",
        lambda **kwargs: {"BINANCE:BTCUSDT": row},
    )

    out = scanner_service.volume_confirmation_analyze("BTCUSDT", "BINANCE", "15m")

    err = out["error"]
    assert err["code"] == "NO_DATA"
    assert err["retryable"] is False
    assert err["message"].startswith("No indicator data for BINANCE:BTCUSDT")


def test_volume_confirmation_upstream_outage_is_retryable(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError(
            "Upstream TradingView scanner returned transient errors on all 3 "
            "attempts spanning 4s."
        )

    monkeypatch.setattr(scanner_service, "get_multiple_analysis", boom)

    out = scanner_service.volume_confirmation_analyze("BTCUSDT", "BINANCE", "15m")

    err = out["error"]
    assert err["code"] == "UPSTREAM_ERROR"
    assert err["retryable"] is True
    assert err["retry_after_s"] == 60
