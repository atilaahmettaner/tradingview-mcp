"""Futures and commodity requests to the TA tools get the right tool, not an error.

The cases below are the hosted server's real calls (30 days to 2026-11-14):
AI clients passed the futures venue as `exchange` (NYMEX CL1!, CME 6E1!,
CBOT_MINI YM1!, COMEX GC1!, CBOE VIX) or asked for commodity/index CFDs the
scanners don't serve (TVC USOIL/UKOIL, OANDA BCOUSD/NATGASUSD/XCUUSD/WTICOUSD,
CAPITALCOM US30). Each failed with INVALID_EXCHANGE, SYMBOL_NOT_FOUND or
NO_DATA. Pure routing assertions plus the three tool entry points; no network.
"""
import asyncio

import pytest

from tradingview_mcp import server
from tradingview_mcp.core.errors import is_error
from tradingview_mcp.core.services.futures_redirect import route_futures_request


def _answer(symbol, exchange, tool="coin_analysis"):
    route = route_futures_request(symbol, exchange, tool)
    assert route is not None and route.answer is not None, (symbol, exchange)
    return route.answer


# ── Routing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("symbol,exchange,contract,category", [
    ("CL1!", "NYMEX", "NYMEX:CL1!", "energy"),
    ("6E1!", "CME", "CME:6E1!", "forex"),
    ("YM1!", "CBOT_MINI", "CBOT_MINI:YM1!", "equity_index"),
    ("HG1!", "COMEX", "COMEX:HG1!", "metals"),
    ("ES1!", "KUCOIN", "CME_MINI:ES1!", "equity_index"),  # futures notation, any venue
    ("CL", "NYMEX", "NYMEX:CL1!", "energy"),             # bare root on a futures venue
    ("NYMEX:CL1!", "KUCOIN", "NYMEX:CL1!", "energy"),     # venue inside the symbol
])
def test_futures_contracts_point_at_their_category_snapshot(symbol, exchange, contract, category):
    out = _answer(symbol, exchange)
    assert out["asset_class"] == "futures"
    assert out["futures_contract"] == contract
    assert out["use_instead"][0] == {"tool": "futures_category_snapshot", "arguments": {"category": category}}
    assert f'futures_category_snapshot(category="{category}")' in out["note"]
    assert "coin_analysis" in out["note"]


@pytest.mark.parametrize("symbol,exchange,contract,category,asset_class", [
    ("USOIL", "TVC", "NYMEX:CL1!", "energy", "commodity"),
    ("UKOIL", "TVC", "ICEEUR:BRN1!", "energy", "commodity"),
    ("WTICOUSD", "oanda", "NYMEX:CL1!", "energy", "commodity"),
    ("BCOUSD", "OANDA", "ICEEUR:BRN1!", "energy", "commodity"),
    ("NATGASUSD", "OANDA", "NYMEX:NG1!", "energy", "commodity"),
    ("XCUUSD", "OANDA", "COMEX:HG1!", "metals", "commodity"),
    ("US30", "capitalcom", "CBOT_MINI:YM1!", "equity_index", "index"),
])
def test_unserved_cfds_point_at_the_futures_contract_on_the_same_underlying(symbol, exchange, contract, category, asset_class):
    out = _answer(symbol, exchange)
    assert out["asset_class"] == asset_class
    assert out["futures_contract"] == contract
    assert out["use_instead"][0]["arguments"] == {"category": category}
    assert "CFD" in out["note"] and contract in out["note"]


def test_vix_on_cboe_points_at_its_quote():
    out = _answer("VIX", "CBOE", tool="combined_analysis")
    assert out["use_instead"][0] == {"tool": "yahoo_price", "arguments": {"symbol": "^VIX"}}
    assert out["futures_contract"] is None
    assert "combined_analysis" in out["note"]


def test_an_unknown_contract_points_at_the_overview_and_watchlist():
    out = _answer("LBS", "CME")  # lumber: a real CME contract this server doesn't list
    assert [c["tool"] for c in out["use_instead"]] == ["futures_market_overview", "futures_watchlist"]
    assert out["futures_contract"] is None


def test_a_later_month_is_answered_with_the_front_month():
    out = _answer("CL2!", "NYMEX")
    assert out["futures_contract"] == "NYMEX:CL1!"
    assert "front month" in out["note"]


@pytest.mark.parametrize("symbol,exchange,expected", [
    ("GC1!", "COMEX", "TVC:GOLD"),
    ("SI1!", "COMEX", "TVC:SILVER"),
    ("PL1!", "NYMEX", "TVC:PLATINUM"),
    ("PA1!", "NYMEX", "TVC:PALLADIUM"),
    ("GC", "COMEX", "TVC:GOLD"),
])
def test_precious_metal_futures_keep_their_analysis_on_tvc(symbol, exchange, expected):
    route = route_futures_request(symbol, exchange, "coin_analysis")
    assert route is not None and route.answer is None
    assert route.exchange == "tvc"
    assert expected in route.note and "futures_category_snapshot" in route.note


@pytest.mark.parametrize("symbol,exchange", [
    ("BTCUSDT", "BINANCE"),
    ("AAPL", "NASDAQ"),
    ("XAUUSD", "OANDA"),     # spot gold: served on TVC:GOLD already
    ("XAGUSD", "OANDA"),
    ("EURUSD", "OANDA"),
    ("DXY", "TVC"),
    ("GOLD", "TVC"),
    ("GC1!", "KUCOIN"),      # the metal alias already resolves this one
    ("CL", "NYSE"),          # Colgate-Palmolive, not crude oil
    ("WTI", "NYSE"),         # W&T Offshore
    ("COPPER", "NYSE"),      # CFD names only count on CFD venues
    ("USOIL", "BINANCE"),
    ("TEL", "BVB"),          # unsupported, but not futures: still INVALID_EXCHANGE
    ("", ""),
])
def test_everything_else_takes_the_normal_path(symbol, exchange):
    assert route_futures_request(symbol, exchange, "coin_analysis") is None


def test_the_answer_is_not_an_error_envelope():
    out = _answer("CL1!", "NYMEX")
    assert "error" not in out and not is_error(out)


# ── Tool entry points ────────────────────────────────────────────────────────

@pytest.fixture
def no_analysis(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not analyse a redirected request")

    monkeypatch.setattr(server, "analyze_coin", boom)
    monkeypatch.setattr(server, "run_multi_timeframe_analysis", boom)


def test_coin_analysis_answers_nymex_crude_with_the_futures_tool(no_analysis):
    out = server.coin_analysis(symbol="CL1!", exchange="NYMEX", timeframe="1h")
    assert not is_error(out)
    assert out["futures_contract"] == "NYMEX:CL1!"


def test_multi_timeframe_analysis_answers_tvc_oil_with_the_futures_tool(no_analysis):
    out = asyncio.run(server.multi_timeframe_analysis(symbol="USOIL", exchange="tvc"))
    assert out["futures_contract"] == "NYMEX:CL1!"
    assert "multi_timeframe_analysis" in out["note"]


def test_combined_analysis_answers_cboe_vix_without_analysing(no_analysis, monkeypatch):
    monkeypatch.setattr(server, "analyze_sentiment", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    out = asyncio.run(server.combined_analysis(symbol="VIX", exchange="CBOE"))
    assert out["use_instead"][0]["tool"] == "yahoo_price"


def test_coin_analysis_runs_comex_gold_on_tvc_and_says_so(monkeypatch):
    seen = {}

    def fake_analyze(symbol, exchange, timeframe):
        seen.update(symbol=symbol, exchange=exchange, timeframe=timeframe)
        return {"symbol": "TVC:GOLD", "exchange": exchange, "timeframe": timeframe}

    monkeypatch.setattr(server, "analyze_coin", fake_analyze)
    out = server.coin_analysis(symbol="GC1!", exchange="COMEX", timeframe="1D")

    assert seen == {"symbol": "GC1!", "exchange": "tvc", "timeframe": "1D"}
    assert out["requested_exchange"] == "COMEX"
    assert "TVC:GOLD" in out["resolution_note"]


def test_coin_analysis_is_unchanged_for_ordinary_requests(monkeypatch):
    seen = {}
    monkeypatch.setattr(server, "analyze_coin",
                        lambda symbol, exchange, timeframe: seen.update(exchange=exchange) or {"ok": True})
    assert server.coin_analysis(symbol="BTCUSDT", exchange="BINANCE", timeframe="4h") == {"ok": True}
    assert seen == {"exchange": "binance"}


def test_an_unsupported_stock_exchange_is_still_invalid(monkeypatch):
    out = server.coin_analysis(symbol="TEL", exchange="BVB", timeframe="1D")
    assert is_error(out) and out["error"]["code"] == "INVALID_EXCHANGE"
