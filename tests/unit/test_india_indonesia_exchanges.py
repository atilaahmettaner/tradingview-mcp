"""India (NSE, BSE) and Indonesia (IDX) routing.

Each exchange name has to agree on the screener market, the TradingView symbol
prefix and the prefix used in its coinlist; a mismatch makes the scanner return
0 rows without an error. The benchmark indices (NIFTY, BANKNIFTY, SENSEX, the
Jakarta Composite) must resolve whatever exchange the caller guessed, because
"analyze NIFTY" rarely comes with the right exchange attached.
"""
import pytest

from tradingview_mcp.core.services.coinlist import load_symbols
from tradingview_mcp.core.utils.validators import (
    get_market_type,
    get_tv_exchange_prefix,
    is_stock_exchange,
    normalize_tradingview_symbol,
    resolve_screener_for_symbol,
    validate_exchange,
)

# exchange name -> (screener market, TradingView prefix)
ROUTES = {
    "nse": ("india", "NSE"),
    "bse": ("india", "BSE"),
    "idx": ("indonesia", "IDX"),
}


@pytest.mark.parametrize("name,route", sorted(ROUTES.items()))
def test_routes_to_the_expected_screener_and_prefix(name, route):
    market, prefix = route
    for spelling in (name, name.upper()):
        validate_exchange(spelling)  # accepted, no INVALID_EXCHANGE
        assert is_stock_exchange(spelling)
        assert get_market_type(spelling) == market
        assert get_tv_exchange_prefix(spelling) == prefix


@pytest.mark.parametrize("name,route", sorted(ROUTES.items()))
def test_coinlist_uses_the_routed_prefix(name, route):
    _, prefix = route
    symbols = load_symbols(name)
    assert len(symbols) >= 500, f"{name}: coinlist missing or truncated"
    assert {s.split(":", 1)[0] for s in symbols} == {prefix}


@pytest.mark.parametrize("alias,symbol,market", [
    ("NIFTY", "NSE:NIFTY", "india"),
    ("nifty50", "NSE:NIFTY", "india"),
    ("^NSEI", "NSE:NIFTY", "india"),
    ("BANKNIFTY", "NSE:BANKNIFTY", "india"),
    ("SENSEX", "BSE:SENSEX", "india"),
    ("^BSESN", "BSE:SENSEX", "india"),
    ("JKSE", "IDX:COMPOSITE", "indonesia"),
    ("IHSG", "IDX:COMPOSITE", "indonesia"),
])
def test_benchmark_indices_resolve_whatever_exchange_was_guessed(alias, symbol, market):
    for exchange in ("nse", "kucoin", "nasdaq"):
        resolved = normalize_tradingview_symbol(alias, exchange)
        assert resolved == symbol
        assert resolve_screener_for_symbol(resolved, exchange) == market
