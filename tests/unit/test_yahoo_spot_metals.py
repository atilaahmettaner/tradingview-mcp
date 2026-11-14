"""Spot precious metals on the Yahoo tools.

Yahoo Finance has no spot gold, silver, platinum or palladium. The symbols
AI clients send for them (XAUUSD=X, spelled like EURUSD=X, plus XAGUSD=X,
XAU=X and plain XAUUSD) answer 404, and XAU-USD is an unrelated token quoted
at 0. On the hosted server every one of those yahoo_price calls failed (39
since 2026-08-16). Yahoo's metals are the front-month futures, so the tools
quote GC=F / SI=F / PL=F / PA=F and say so in the result.

No network: Yahoo is an httpx.MockTransport that knows only the futures.
"""
from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import unquote

import httpx
import pytest

from tradingview_mcp import server
from tradingview_mcp.core.services import yahoo_finance_service as yfs
from tradingview_mcp.core.utils.validators import (
    normalize_yahoo_symbol,
    yahoo_metal_futures,
)

METAL_FORMS = [
    # The four forms that failed on the hosted server.
    ("XAUUSD=X", "GC=F"),
    ("XAGUSD=X", "SI=F"),
    ("XAUUSD", "GC=F"),
    ("XAU=X", "GC=F"),
    # Their siblings and the other pair spellings.
    ("XPTUSD=X", "PL=F"),
    ("XPDUSD=X", "PA=F"),
    ("XAG=X", "SI=F"),
    ("XAU-USD", "GC=F"),
    ("XAU/USD", "GC=F"),
    ("XPT/USD", "PL=F"),
    ("XPD-USD", "PA=F"),
    ("XAUUSDT", "GC=F"),
    ("XAU-USDT", "GC=F"),
    ("XAG/USDT", "SI=F"),
    # Behind an EXCHANGE: prefix, in any case, with stray whitespace.
    ("OANDA:XAUUSD", "GC=F"),
    ("FX_IDC:XAGUSD", "SI=F"),
    ("TVC:XPTUSD", "PL=F"),
    ("oanda:xpdusd", "PA=F"),
    ("  xauusd=x ", "GC=F"),
]

UNCHANGED = [
    "GC=F", "SI=F", "PL=F", "PA=F",   # already Yahoo's metals
    "EURUSD=X", "JPY=X",              # real FX pairs
    "BTC-USD", "AAPL", "^GSPC", "THYAO.IS",
    "GOLD",                           # a stock ticker, not the metal
    "XAU", "XAG", "^XAU",             # bare codes and an index ticker
    "XAUT-USD", "PAXG-USD",           # gold-backed tokens, not spot gold
    "XAUEUR=X",                       # not a USD pair: outside the rule
    "NASDAQ:AAPL",                    # no general prefix stripping
]


# ── Resolution ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,futures", METAL_FORMS)
def test_spot_metal_resolves_to_front_month_futures(raw, futures):
    assert normalize_yahoo_symbol(raw) == futures
    ticker, note = yahoo_metal_futures(raw)
    assert ticker == futures
    assert f"futures {futures}" in note
    assert "not spot" in note


def test_never_resolves_to_the_xau_usd_token():
    """XAU-USD on Yahoo is a token quoted at 0, not gold."""
    resolved = {normalize_yahoo_symbol(raw) for raw, _ in METAL_FORMS}
    assert resolved == {"GC=F", "SI=F", "PL=F", "PA=F"}
    assert normalize_yahoo_symbol("XAU-USD") == "GC=F"


@pytest.mark.parametrize("raw", UNCHANGED)
def test_other_symbols_are_unchanged(raw):
    assert normalize_yahoo_symbol(raw) == raw
    assert yahoo_metal_futures(raw) is None


def test_existing_aliases_still_win():
    assert normalize_yahoo_symbol("TWSE:TAIEX") == "^TWII"


def test_note_names_the_metal_and_the_symbol_asked_for():
    _, note = yahoo_metal_futures("OANDA:XAGUSD")
    assert note.startswith("Yahoo Finance has no spot silver price for XAGUSD,")
    assert "silver futures SI=F (front month)" in note


# ── yahoo_price against a fake Yahoo ─────────────────────────────────────────

# Five daily bars, newest last; the quote is fresh, so it drives the price.
_TS = [1762732800, 1762819200, 1762905600, 1762992000, 1763078400]
_FUTURES = {"GC=F": 4080.5, "SI=F": 50.25, "PL=F": 1580.0, "PA=F": 1435.0}


def _chart(symbol: str) -> dict:
    price = _FUTURES[symbol]
    return {
        "meta": {
            "symbol": symbol,
            "currency": "USD",
            "exchangeName": "CMX",
            "instrumentType": "FUTURE",
            "regularMarketPrice": price,
            "regularMarketTime": _TS[-1] + 3600,
            "marketState": "REGULAR",
        },
        "timestamp": _TS,
        "indicators": {"quote": [{"close": [price - 4, price - 3, price - 2, price - 1, price]}]},
    }


@pytest.fixture
def fake_yahoo(monkeypatch):
    """Yahoo's chart endpoint: 200 for the futures, 404 for anything else.
    Returns the list of symbols requested."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        symbol = unquote(request.url.path).rsplit("/", 1)[-1]
        requested.append(symbol)
        if symbol in _FUTURES:
            return httpx.Response(200, json={"chart": {"result": [_chart(symbol)], "error": None}})
        return httpx.Response(404, json={"chart": {"result": None, "error": {"code": "Not Found"}}})

    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        kwargs.pop("proxy", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(yfs, "httpx", SimpleNamespace(AsyncClient=client))
    monkeypatch.setattr(yfs, "get_httpx_proxy", lambda: None)
    return requested


async def test_the_spot_symbol_itself_is_a_404(fake_yahoo):
    """What the hosted server logged: the symbol goes to Yahoo as typed."""
    result = await yfs.get_price_async("XAUUSD=X")
    assert "404 Not Found" in result["error"]
    assert fake_yahoo == ["XAUUSD=X"]


@pytest.mark.parametrize("raw,futures", [
    ("XAUUSD=X", "GC=F"), ("XAGUSD=X", "SI=F"), ("XAUUSD", "GC=F"), ("XAU=X", "GC=F"),
    ("OANDA:XPTUSD", "PL=F"), ("XPD/USD", "PA=F"),
])
async def test_yahoo_price_quotes_the_futures_and_says_so(fake_yahoo, raw, futures):
    result = await server.yahoo_price(raw)

    assert fake_yahoo == [futures]           # one request, to the futures
    assert "error" not in result
    assert result["symbol"] == futures
    assert result["price"] == _FUTURES[futures]
    assert result["requested_symbol"] == raw.strip().upper()
    assert f"futures {futures} (front month), not spot" in result["note"]


async def test_yahoo_price_keeps_the_note_when_the_futures_fetch_fails(monkeypatch):
    async def failing(symbol: str) -> dict:
        return {"symbol": symbol, "error": "timed out", "source": "Yahoo Finance"}

    monkeypatch.setattr(server, "get_price_async", failing)
    result = await server.yahoo_price("XAUUSD=X")
    assert result["error"] == "timed out"
    assert result["symbol"] == "GC=F"
    assert "not spot" in result["note"]


async def test_yahoo_price_other_symbols_have_no_note(fake_yahoo):
    result = await server.yahoo_price("GC=F")
    assert fake_yahoo == ["GC=F"]
    assert "note" not in result
    assert "requested_symbol" not in result
