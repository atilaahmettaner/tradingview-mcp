import pytest

from tradingview_mcp.core.errors import ErrorCode, ScreenerServiceError
from tradingview_mcp.core.utils.validators import sanitize_timeframe, validate_timeframe


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
    assert sanitize_timeframe("1h") == "1h"
    assert sanitize_timeframe("4h") == "4h"


def test_sanitize_timeframe_falls_back_to_default():
    assert sanitize_timeframe("invalid", "15m") == "15m"


@pytest.mark.parametrize("code,expected", [
    ("5", "5m"), ("15", "15m"), ("60", "1h"), ("240", "4h"),
    ("1440", "1D"), ("D", "1D"), ("d", "1D"), ("W", "1W"), (" 60 ", "1h"),
])
def test_tradingview_numeric_interval_codes_map_to_supported_timeframes(code, expected):
    # Integrations send TradingView's native codes; "60" used to silently
    # become the 15m default, and then started raising INVALID_TIMEFRAME.
    assert validate_timeframe(code) == expected
    assert sanitize_timeframe(code) == expected


@pytest.mark.parametrize("code", ["30m", "30", "120", "7", "1s"])
def test_unsupported_timeframes_still_raise(code):
    with pytest.raises(ScreenerServiceError) as exc:
        validate_timeframe(code)
    assert exc.value.code == ErrorCode.INVALID_TIMEFRAME

