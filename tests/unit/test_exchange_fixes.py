"""
Tests for Bug 1 and Bug 2 fixes:
  - Bug 1: multi_timeframe_analysis ignored exchange parameter (hardcoded KUCOIN prefix)
  - Bug 2: combined_analysis / coin_analysis did not recognise AMEX/NYSEARCA/PCX aliases
"""
from tradingview_mcp.core.utils.validators import (
    sanitize_exchange,
    get_tv_exchange_prefix,
    EXCHANGE_SCREENER,
    STOCK_EXCHANGES,
)


# ── Bug 1 fix: exchange aliases now accepted by sanitize_exchange ──────────────

class TestSanitizeExchangeNewAliases:
    """sanitize_exchange must recognise AMEX, NYSEARCA, PCX as valid exchanges."""

    def test_amex_is_valid_exchange(self):
        assert sanitize_exchange("AMEX", "KUCOIN") == "amex"

    def test_nysearca_is_valid_exchange(self):
        assert sanitize_exchange("NYSEARCA", "KUCOIN") == "nysearca"

    def test_pcx_is_valid_exchange(self):
        assert sanitize_exchange("PCX", "KUCOIN") == "pcx"

    def test_amex_lowercase_is_valid_exchange(self):
        assert sanitize_exchange("amex", "KUCOIN") == "amex"

    def test_unknown_exchange_still_falls_back_to_default(self):
        assert sanitize_exchange("INVALID_EXCHANGE", "KUCOIN") == "KUCOIN"

    def test_twse_still_valid(self):
        assert sanitize_exchange("TWSE", "KUCOIN") == "twse"

    def test_tpex_still_valid(self):
        assert sanitize_exchange("TPEX", "KUCOIN") == "tpex"


class TestExchangeScreenerNewEntries:
    """AMEX/NYSEARCA/PCX must map to the america screener."""

    def test_amex_maps_to_america_screener(self):
        assert EXCHANGE_SCREENER["amex"] == "america"

    def test_nysearca_maps_to_america_screener(self):
        assert EXCHANGE_SCREENER["nysearca"] == "america"

    def test_pcx_maps_to_america_screener(self):
        assert EXCHANGE_SCREENER["pcx"] == "america"

    def test_amex_in_stock_exchanges(self):
        assert "amex" in STOCK_EXCHANGES

    def test_nysearca_in_stock_exchanges(self):
        assert "nysearca" in STOCK_EXCHANGES

    def test_pcx_in_stock_exchanges(self):
        assert "pcx" in STOCK_EXCHANGES


# ── Bug 2 fix: get_tv_exchange_prefix returns correct TradingView prefix ──────

class TestGetTvExchangePrefix:
    """get_tv_exchange_prefix must return AMEX for all NYSE Arca aliases."""

    def test_amex_returns_AMEX_prefix(self):
        assert get_tv_exchange_prefix("amex") == "AMEX"

    def test_nysearca_returns_AMEX_prefix(self):
        """NYSEARCA should resolve to AMEX (TradingView's canonical prefix for NYSE Arca)."""
        assert get_tv_exchange_prefix("nysearca") == "AMEX"

    def test_pcx_returns_AMEX_prefix(self):
        """PCX (Pacific Exchange MIC code) should resolve to AMEX."""
        assert get_tv_exchange_prefix("pcx") == "AMEX"

    def test_nasdaq_returns_NASDAQ_prefix(self):
        assert get_tv_exchange_prefix("nasdaq") == "NASDAQ"

    def test_nyse_returns_NYSE_prefix(self):
        assert get_tv_exchange_prefix("nyse") == "NYSE"

    def test_twse_returns_TWSE_prefix(self):
        assert get_tv_exchange_prefix("twse") == "TWSE"

    def test_tpex_returns_TPEX_prefix(self):
        assert get_tv_exchange_prefix("tpex") == "TPEX"

    def test_crypto_exchange_returns_uppercase_fallback(self):
        """Crypto exchanges not in the map fall back to exchange.upper()."""
        assert get_tv_exchange_prefix("kucoin") == "KUCOIN"
        assert get_tv_exchange_prefix("binance") == "BINANCE"
        assert get_tv_exchange_prefix("bybit") == "BYBIT"


# ── End-to-end symbol construction simulation ─────────────────────────────────

class TestSymbolConstruction:
    """Simulate how multi_timeframe_analysis and coin_analysis build the TradingView symbol."""

    def _build_symbol(self, raw_exchange: str, raw_symbol: str) -> str:
        exchange = sanitize_exchange(raw_exchange, "KUCOIN")
        prefix = get_tv_exchange_prefix(exchange)
        return f"{prefix}:{raw_symbol.upper()}"

    def test_gdx_with_amex_exchange(self):
        """Bug 1 regression: GDX on AMEX must produce AMEX:GDX, not KUCOIN:GDX."""
        assert self._build_symbol("AMEX", "GDX") == "AMEX:GDX"

    def test_gdx_with_nysearca_exchange(self):
        """Bug 2 regression: NYSEARCA alias must also produce AMEX:GDX."""
        assert self._build_symbol("NYSEARCA", "GDX") == "AMEX:GDX"

    def test_gdx_with_pcx_exchange(self):
        assert self._build_symbol("PCX", "GDX") == "AMEX:GDX"

    def test_gld_with_amex_exchange(self):
        assert self._build_symbol("AMEX", "GLD") == "AMEX:GLD"

    def test_xle_with_amex_exchange(self):
        assert self._build_symbol("AMEX", "XLE") == "AMEX:XLE"

    def test_nyse_stock_uses_nyse_prefix(self):
        """Regular NYSE stocks must still get NYSE prefix."""
        assert self._build_symbol("NYSE", "DOCN") == "NYSE:DOCN"

    def test_nasdaq_stock_uses_nasdaq_prefix(self):
        assert self._build_symbol("NASDAQ", "TSLA") == "NASDAQ:TSLA"

    def test_twse_stock_uses_twse_prefix(self):
        """Taiwan stocks must use TWSE prefix."""
        assert self._build_symbol("TWSE", "2330") == "TWSE:2330"

    def test_tpex_stock_uses_tpex_prefix(self):
        assert self._build_symbol("TPEX", "3105") == "TPEX:3105"

    def test_crypto_with_kucoin(self):
        """Crypto fallback must still work."""
        assert self._build_symbol("KUCOIN", "BTCUSDT") == "KUCOIN:BTCUSDT"

    def test_unknown_exchange_still_falls_back_to_kucoin(self):
        """Unrecognised exchange falls back to KUCOIN default then gets KUCOIN prefix."""
        assert self._build_symbol("INVALID", "GDX") == "KUCOIN:GDX"


# ── Bug 3 fix: volume_confirmation_analyze sent bare crypto symbols ────────────
# It hand-rolled symbol normalisation and only prefixed the venue for STOCK
# exchanges, so crypto symbols reached tradingview_ta as a bare ticker
# ("BTCUSDT") and were rejected — ~99% of volume_confirmation_analysis calls
# failed. It now uses the canonical normalize_tradingview_symbol() like
# analyze_coin(). These tests capture the symbol actually sent upstream (no
# network) and assert it is fully qualified.

class TestVolumeConfirmationSymbolPrefix:
    @staticmethod
    def _capture(symbol, exchange):
        import tradingview_mcp.core.services.scanner_service as svc
        seen = {}

        def fake_gma(screener, interval, symbols):
            seen["symbols"] = symbols
            seen["screener"] = screener
            return {}  # empty -> function returns a "No data" envelope after the call

        orig = svc.get_multiple_analysis
        svc.get_multiple_analysis = fake_gma
        try:
            svc.volume_confirmation_analyze(symbol, exchange, "15m")
        finally:
            svc.get_multiple_analysis = orig
        return seen

    def test_crypto_symbol_is_venue_prefixed(self):
        seen = self._capture("BTCUSDT", "KUCOIN")
        assert seen["symbols"] == ["KUCOIN:BTCUSDT"]  # not bare "BTCUSDT"
        assert seen["screener"] == "crypto"

    def test_stock_symbol_is_venue_prefixed(self):
        seen = self._capture("AAPL", "NASDAQ")
        assert seen["symbols"] == ["NASDAQ:AAPL"]
        assert seen["screener"] == "america"

    def test_commodity_alias_resolves(self):
        # XAUUSD must resolve to the TradingView commodity symbol, not get a
        # spurious USDT suffix (the old code did "XAUUSD" -> "XAUUSDUSDT").
        seen = self._capture("XAUUSD", "KUCOIN")
        assert seen["symbols"] == ["TVC:GOLD"]
        assert seen["screener"] == "cfd"
