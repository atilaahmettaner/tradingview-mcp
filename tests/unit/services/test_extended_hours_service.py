"""Unit tests for extended_hours_service._shape_extended_hours.

Regression tests for the pre-open previous-close bug: before the open,
Yahoo's `previousClose`/`chartPreviousClose` still refer to the session
before last while the pre-market bars already belong to the new day, so
`change_vs_previous_close_pct` could carry the wrong sign (SPY showed
+0.30 when the true pre-market change was -0.13; QQQ +0.73 vs -0.47).
In that window the pre-market change is measured against the last
regular close (`regularMarketPrice`), shown as `reference_close`.
`previous_close` and the regular change keep Yahoo's reference, so before
the open they still describe the last session's own move. After the open,
`previousClose` is correct for everything and the old behaviour holds.
"""
from tradingview_mcp.core.services.extended_hours_service import _shape_extended_hours

_REGULAR_START = 1_792_147_800
_REGULAR_END = _REGULAR_START + 23_400  # 6.5h session


def _payload(*, regular_market_time, regular_market_price, previous_close,
             timestamps, closes, market_state="PRE"):
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "USD",
                        "exchangeName": "NASDAQ",
                        "marketState": market_state,
                        "regularMarketPrice": regular_market_price,
                        "regularMarketTime": regular_market_time,
                        "previousClose": previous_close,
                        "chartPreviousClose": previous_close,
                        "currentTradingPeriod": {
                            "regular": {
                                "start": _REGULAR_START,
                                "end": _REGULAR_END,
                            }
                        },
                    },
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


def test_preopen_pre_market_uses_last_regular_close_spy():
    """Issue example: SPY pre-market -0.13% vs last close, not +0.30%."""
    data = _payload(
        regular_market_time=_REGULAR_START - 63_000,  # prior session's close
        regular_market_price=590.00,                  # last regular close
        previous_close=587.46,                        # stale: two sessions back
        timestamps=[_REGULAR_START - 3_600, _REGULAR_START - 60],
        closes=[589.50, 589.23],
    )
    out = _shape_extended_hours("SPY", data)
    assert out["pre_market"]["change_vs_previous_close_pct"] == -0.13
    assert out["pre_market"]["reference_close"] == 590.00


def test_preopen_pre_market_uses_last_regular_close_qqq():
    """Issue example: QQQ pre-market -0.47% vs last close, not +0.73%."""
    data = _payload(
        regular_market_time=_REGULAR_START - 63_000,
        regular_market_price=500.00,
        previous_close=494.04,
        timestamps=[_REGULAR_START - 3_600, _REGULAR_START - 60],
        closes=[498.10, 497.65],
    )
    out = _shape_extended_hours("QQQ", data)
    assert out["pre_market"]["change_vs_previous_close_pct"] == -0.47
    assert out["pre_market"]["reference_close"] == 500.00


def test_preopen_regular_change_still_shows_the_last_session():
    """Before the open the regular block is the last session: its change stays
    measured from Yahoo's previous close (+0.43%), it doesn't collapse to 0."""
    data = _payload(
        regular_market_time=_REGULAR_START - 63_000,
        regular_market_price=590.00,
        previous_close=587.46,
        timestamps=[_REGULAR_START - 3_600, _REGULAR_START - 60],
        closes=[589.50, 589.23],
    )
    out = _shape_extended_hours("SPY", data)
    assert out["previous_close"] == 587.46
    assert out["regular"]["price"] == 590.00
    assert out["regular"]["change_pct"] == 0.43


def test_postopen_previous_close_unchanged():
    """After the open, `previousClose` is the correct reference — keep it."""
    data = _payload(
        regular_market_time=_REGULAR_START + 3_600,  # inside today's session
        regular_market_price=591.00,
        previous_close=590.00,
        timestamps=[_REGULAR_START - 60, _REGULAR_START + 60],
        closes=[589.90, 591.00],
        market_state="REGULAR",
    )
    out = _shape_extended_hours("SPY", data)
    assert out["previous_close"] == 590.00
    assert out["regular"]["change_pct"] == 0.17
    assert out["pre_market"]["reference_close"] == 590.00


def test_missing_regular_market_time_falls_back_to_previous_close():
    """No regularMarketTime in meta -> old behaviour, no crash."""
    data = _payload(
        regular_market_time=_REGULAR_START - 63_000,
        regular_market_price=590.00,
        previous_close=587.46,
        timestamps=[_REGULAR_START - 60],
        closes=[589.23],
    )
    del data["chart"]["result"][0]["meta"]["regularMarketTime"]
    out = _shape_extended_hours("SPY", data)
    assert out["previous_close"] == 587.46
    assert out["pre_market"]["reference_close"] == 587.46
