"""Strict input validation at the MCP tool boundary.

sanitize_exchange/timeframe silently substituted the default on bad input —
an LLM asking for KRAKEN got KUCOIN data with no indication anything was
wrong. Tools now return INVALID_EXCHANGE / INVALID_TIMEFRAME envelopes that
list valid values, so callers can self-correct. Aliases ("1d" → "1D") and
omitted parameters still resolve silently.
"""
from __future__ import annotations

import asyncio

import pytest

from tradingview_mcp import server
from tradingview_mcp.core.errors import ScreenerServiceError
from tradingview_mcp.core.utils.validators import validate_exchange, validate_timeframe


class TestValidators:
    def test_valid_and_aliased_inputs_pass(self):
        assert validate_exchange("BINANCE", "kucoin") == "binance"
        assert validate_exchange("", "kucoin") == "kucoin"
        assert validate_timeframe("1d", "5m") == "1D"
        assert validate_timeframe(" 4H ", "5m") == "4h"
        assert validate_timeframe("", "15m") == "15m"

    def test_unknown_exchange_raises_with_valid_list(self):
        with pytest.raises(ScreenerServiceError) as exc_info:
            validate_exchange("KRAKEN", "kucoin")
        env = exc_info.value.to_envelope()
        assert env["error"]["code"] == "INVALID_EXCHANGE"
        assert "binance" in env["error"]["valid_exchanges"]
        assert env["error"]["retryable"] is False

    def test_unknown_timeframe_raises_with_valid_list(self):
        with pytest.raises(ScreenerServiceError) as exc_info:
            validate_timeframe("30m", "15m")
        env = exc_info.value.to_envelope()
        assert env["error"]["code"] == "INVALID_TIMEFRAME"
        assert "1D" in env["error"]["valid_timeframes"]


class TestToolBoundary:
    def test_top_gainers_returns_invalid_exchange_envelope(self):
        result = asyncio.run(server.top_gainers(exchange="KRAKEN"))
        assert result["error"]["code"] == "INVALID_EXCHANGE"

    def test_coin_analysis_returns_invalid_timeframe_envelope(self):
        result = server.coin_analysis("BTCUSDT", exchange="KUCOIN", timeframe="30m")
        assert result["error"]["code"] == "INVALID_TIMEFRAME"

    def test_egx_tool_returns_invalid_timeframe_envelope(self):
        result = server.egx_market_overview(timeframe="2h")
        assert result["error"]["code"] == "INVALID_TIMEFRAME"

    def test_combined_analysis_rejects_bad_exchange(self):
        result = asyncio.run(server.combined_analysis("AAPL", exchange="NOPE"))
        assert result["error"]["code"] == "INVALID_EXCHANGE"


class TestCombinedAnalysisLegFailure:
    def test_one_failing_leg_degrades_not_crashes(self, monkeypatch):
        def ok_tech(symbol, exchange, timeframe):
            return {"market_sentiment": {"momentum": "Bullish", "buy_sell_signal": "BUY"}}

        def boom_sentiment(symbol, category):
            raise RuntimeError("marketaux down")

        def ok_news(symbol, category, limit):
            return {"count": 1, "items": [{"title": "x"}]}

        monkeypatch.setattr(server, "analyze_coin", ok_tech)
        monkeypatch.setattr(server, "analyze_sentiment", boom_sentiment)
        monkeypatch.setattr(server, "fetch_news_summary", ok_news)

        result = asyncio.run(server.combined_analysis("AAPL", exchange="NASDAQ"))

        # Whole-tool result survives; only the failed leg carries an envelope.
        assert result["technical"]["market_sentiment"]["momentum"] == "Bullish"
        assert result["sentiment"]["error"]["code"] == "INTERNAL_ERROR"
        assert result["news"]["count"] == 1


class TestFuturesDirectionValidation:
    def test_typo_direction_errors_instead_of_returning_losers(self):
        from tradingview_mcp.core.services.futures_service import get_futures_movers

        result = get_futures_movers(direction="gainer")
        assert "error" in result
        assert "gainers" in result["error"]
