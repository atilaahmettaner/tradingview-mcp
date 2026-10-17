"""Unit tests for backtest numeric-input validation.

These cover the capital/cost guards added to the public backtest API. They are
network-free on purpose: each guard runs *before* `_fetch_ohlcv`, so passing a
valid strategy/period/interval with an out-of-range numeric input raises a
typed error without ever hitting Yahoo Finance.
"""
import pytest

from tradingview_mcp.core.errors import (
    BacktestServiceError,
    ErrorCode,
    is_error,
)
from tradingview_mcp.core.services.backtest_service import (
    _validate_numeric_inputs,
    compare_strategies,
    run_backtest,
    walk_forward_backtest,
)

# ─── helper: _validate_numeric_inputs ─────────────────────────────────────────

def test_valid_inputs_pass():
    assert _validate_numeric_inputs(10_000.0, 0.1, 0.05) is None


def test_zero_capital_rejected():
    msg = _validate_numeric_inputs(0.0, 0.1, 0.05)
    assert msg is not None and "initial_capital" in msg


def test_negative_capital_rejected():
    msg = _validate_numeric_inputs(-100.0, 0.1, 0.05)
    assert msg is not None and "initial_capital" in msg


def test_negative_commission_rejected():
    # Negative cost would credit the account every trade, inflating returns.
    msg = _validate_numeric_inputs(10_000.0, -0.1, 0.05)
    assert msg is not None and "commission_pct" in msg


def test_negative_slippage_rejected():
    msg = _validate_numeric_inputs(10_000.0, 0.1, -0.05)
    assert msg is not None and "slippage_pct" in msg


def test_absurd_cost_rejected():
    # Out of range: a value passed in basis points (250) instead of percent (2.5).
    msg = _validate_numeric_inputs(10_000.0, 250.0, 0.05)
    assert msg is not None and "commission_pct" in msg


def test_cost_boundaries_inclusive():
    assert _validate_numeric_inputs(10_000.0, 0.0, 0.0) is None
    assert _validate_numeric_inputs(10_000.0, 100.0, 100.0) is None


# ─── boundary: public API returns error before any network call ───────────────

def test_run_backtest_rejects_bad_capital_offline():
    with pytest.raises(BacktestServiceError) as exc_info:
        run_backtest("BTC-USD", "rsi", period="1y", interval="1d",
                     initial_capital=0.0)
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER
    env = exc_info.value.to_envelope()
    assert is_error(env)
    assert "initial_capital" in env["error"]["message"]
    assert env["error"]["retryable"] is False


def test_walk_forward_rejects_negative_commission_offline():
    with pytest.raises(BacktestServiceError) as exc_info:
        walk_forward_backtest("BTC-USD", "rsi", period="2y", interval="1d",
                              commission_pct=-0.1)
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER
    env = exc_info.value.to_envelope()
    assert is_error(env)
    assert "commission_pct" in env["error"]["message"]


def test_compare_strategies_rejects_bad_capital_offline():
    with pytest.raises(BacktestServiceError) as exc_info:
        compare_strategies("BTC-USD", period="1y", interval="1d",
                           initial_capital=-5.0)
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER
    env = exc_info.value.to_envelope()
    assert is_error(env)
    assert "initial_capital" in env["error"]["message"]
