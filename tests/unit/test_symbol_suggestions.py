"""exchanges_listing_symbol() — local-coinlist exchange suggestions.

These suggestions power the SYMBOL_NOT_FOUND error envelope. Grounded in a
real production failure: agents retried "HYPEUSDT on BINANCE" 50+ times
because the old bare-string error offered no alternative and no retryability
signal. HYPEUSDT ships in the bundled kucoin/mexc/huobi coinlists but not in
binance's — so the suggestion set below is asserted against the real files.
"""
from tradingview_mcp.core.services.coinlist import exchanges_listing_symbol


def test_hype_suggests_real_listings_not_binance():
    listed = exchanges_listing_symbol("HYPEUSDT")
    assert "KUCOIN" in listed
    assert "MEXC" in listed
    assert "BINANCE" not in listed


def test_prefixed_symbol_matches_bare_symbol():
    assert exchanges_listing_symbol("BINANCE:HYPEUSDT") == exchanges_listing_symbol("HYPEUSDT")


def test_case_insensitive():
    assert exchanges_listing_symbol("hypeusdt") == exchanges_listing_symbol("HYPEUSDT")


def test_unknown_symbol_returns_empty():
    assert exchanges_listing_symbol("ZZZQQQ123XYZ") == []


def test_blank_symbol_returns_empty():
    assert exchanges_listing_symbol("") == []
    assert exchanges_listing_symbol("BINANCE:") == []


def test_aggregate_all_list_never_suggested():
    # all.txt contains every symbol; suggesting "ALL" as an exchange would
    # steer the model into an invalid `exchange` value.
    listed = exchanges_listing_symbol("BTCUSDT")
    assert "ALL" not in listed


def test_max_results_cap():
    listed = exchanges_listing_symbol("BTCUSDT", max_results=2)
    assert len(listed) <= 2
