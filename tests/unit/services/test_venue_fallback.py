"""Auto-venue fallback (the HYPEUSDT@binance pattern).

7-day telemetry: 121 errors from ONE paying customer's hourly automation
requesting HYPEUSDT on binance — the SYMBOL_NOT_FOUND envelope named the
right venues (HUOBI/KUCOIN/MEXC) but the automation never read it. When the
requested venue doesn't list a ticker that another venue does, we now run
the analysis on a listing venue and say so in the response
(requested_exchange / resolved_exchange / resolution_note) instead of
failing a deterministic request forever.

Network-free: the upstream fetch (get_multiple_analysis in screener_service,
resilient_scan_columns in scanner_service) is monkeypatched.
"""
from collections import defaultdict
from types import SimpleNamespace

from tradingview_mcp.core.errors import is_error
from tradingview_mcp.core.services import scanner_service, screener_service
from tradingview_mcp.core.services.screener_service import pick_fallback_exchange


def _fake_data():
    # analyze_coin reads dozens of indicator keys; defaultdict(None) keeps any
    # .get()/[] access safe while we pin only the fallback envelope fields.
    ind = defaultdict(lambda: None)
    ind.update({
        "close": 42.5, "open": 41.0, "high": 43.0, "low": 40.5, "volume": 1_000_000.0,
        "RSI": 55.0, "ATR": 1.2, "change": 2.1, "Recommend.All": 0.4,
        "MACD.macd": 0.5, "MACD.signal": 0.3, "EMA20": 41.8, "EMA50": 40.9,
        "SMA20": 41.5, "BB.upper": 44.0, "BB.lower": 39.0,
    })
    return SimpleNamespace(indicators=ind, summary={"RECOMMENDATION": "BUY"},
                           time=None, exchange="KUCOIN", symbol="HYPEUSDT")


# ── pick_fallback_exchange (pure) ─────────────────────────────────────────────

def test_prefers_kucoin_over_alphabetical_huobi():
    # HYPEUSDT's coinlist venues are HUOBI/KUCOIN/MEXC (alphabetical) — the
    # preference order must pick KUCOIN, not HUOBI.
    assert pick_fallback_exchange("HYPEUSDT", "binance") == "KUCOIN"


def test_no_listing_anywhere_returns_none():
    assert pick_fallback_exchange("DEFINITELYNOTACOIN123", "binance") is None


def test_requested_venue_is_never_suggested_back():
    alt = pick_fallback_exchange("HYPEUSDT", "KUCOIN")
    assert alt != "KUCOIN"


# ── analyze_coin fallback ─────────────────────────────────────────────────────

def test_analyze_coin_resolves_on_listing_venue(monkeypatch):
    calls = []

    def fake_gma(screener, interval, symbols):
        calls.append(symbols[0])
        if symbols[0].startswith("BINANCE:"):
            return {}                       # requested venue: not listed
        return {symbols[0]: _fake_data()}   # fallback venue: real row

    monkeypatch.setattr(screener_service, "get_multiple_analysis", fake_gma)
    out = screener_service.analyze_coin("HYPEUSDT", "binance", "15m")
    assert not is_error(out), out
    assert out["requested_exchange"] == "binance"
    assert out["resolved_exchange"] == "KUCOIN"
    assert "not listed on binance" in out["resolution_note"]
    assert calls[0].startswith("BINANCE:") and calls[1].startswith("KUCOIN:")


def test_analyze_coin_still_errors_when_fallback_venue_is_empty_too(monkeypatch):
    monkeypatch.setattr(screener_service, "get_multiple_analysis",
                        lambda screener, interval, symbols: {})
    out = screener_service.analyze_coin("HYPEUSDT", "binance", "15m")
    assert is_error(out)
    assert out["error"]["code"] == "SYMBOL_NOT_FOUND"


# ── volume_confirmation fallback (incl. the NO_DATA row-without-indicators) ──

def test_volume_confirmation_resolves_on_listing_venue(monkeypatch):
    def fake_scan(screener, interval, symbols, columns):
        if symbols[0].startswith("BINANCE:"):
            # the live NO_DATA shape: the venue knows the row but has no values
            return {symbols[0]: {c: None for c in columns}}
        ind = _fake_data().indicators
        return {symbols[0]: {c: ind[c] for c in columns}}

    monkeypatch.setattr(scanner_service, "resilient_scan_columns", fake_scan)
    out = scanner_service.volume_confirmation_analyze("HYPEUSDT", "binance", "15m")
    assert not is_error(out), out
    assert out["resolved_exchange"] == "KUCOIN"
    assert out["requested_exchange"] == "binance"
