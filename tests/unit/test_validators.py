from tradingview_mcp.core.utils.validators import sanitize_timeframe


def test_sanitize_timeframe_accepts_lowercase_day_week_month():
    assert sanitize_timeframe("1d") == "1D"
    assert sanitize_timeframe("1w") == "1W"
    assert sanitize_timeframe("1m") == "1M"


def test_sanitize_timeframe_accepts_uppercase_with_whitespace():
    assert sanitize_timeframe(" 1D ") == "1D"
    assert sanitize_timeframe(" 1W ") == "1W"
    assert sanitize_timeframe(" 1M ") == "1M"


def test_sanitize_timeframe_preserves_intraday_timeframes():
    assert sanitize_timeframe("5m") == "5m"
    assert sanitize_timeframe("15m") == "15m"
    assert sanitize_timeframe("30m") == "30m"
    assert sanitize_timeframe("1h") == "1h"
    assert sanitize_timeframe("4h") == "4h"


def test_sanitize_timeframe_falls_back_to_default():
    assert sanitize_timeframe("invalid", "15m") == "15m"
