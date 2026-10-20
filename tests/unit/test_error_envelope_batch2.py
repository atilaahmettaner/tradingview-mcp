"""Issue #76 batch 2: backtest trio tools return envelopes on EVERY failure.

Before this batch the three backtest tools (`backtest_strategy`,
`compare_strategies`, `walk_forward_backtest_strategy`) returned legacy
``{"error": "some string"}`` dicts from ~23 return sites in the service
layer, and the server handlers had no try/except at all — a fetch crash
or an unexpected exception escaped raw to the MCP layer.

These tests pin the uniform contract: every failure mode → structured
envelope with a stable ``code`` and an explicit ``retryable`` flag.
All network-free (service functions are monkeypatched at the server
module boundary, matching test_error_envelope_batch1.py's pattern).
"""
import pytest

from tradingview_mcp import server
from tradingview_mcp.core.errors import (
    BacktestServiceError,
    ErrorCode,
    exception_to_envelope,
    is_error,
)


def _boom_backtest(*args, **kwargs):
    raise BacktestServiceError(
        ErrorCode.UPSTREAM_ERROR, "Failed to fetch data for 'AAPL': timeout",
        symbol="AAPL", retryable=True,
    )


def _boom_invalid(*args, **kwargs):
    raise BacktestServiceError(
        ErrorCode.INVALID_PARAMETER, "Unknown strategy 'nope'. Choose: rsi",
        strategy="nope", retryable=False,
    )


def _boom_unexpected(*args, **kwargs):
    raise ValueError("someone divided by a dataframe")


# ── translator unit behavior ───────────────────────────────────────────────────

def test_backtest_service_error_is_a_runtime_error():
    # Backward-compat pin: the pre-envelope service guards returned error
    # dicts, and any caller treating those as fatal (or catching
    # RuntimeError from deeper helpers) must keep working.
    assert issubclass(BacktestServiceError, RuntimeError)


def test_translator_maps_backtest_error_with_retryable_true():
    exc = BacktestServiceError(
        ErrorCode.UPSTREAM_ERROR, "Failed to fetch data for 'AAPL': timeout",
        symbol="AAPL", retryable=True,
    )
    env = exception_to_envelope(exc)
    assert is_error(env)
    assert env["error"]["code"] == "UPSTREAM_ERROR"
    assert env["error"]["retryable"] is True
    assert env["error"]["symbol"] == "AAPL"


def test_translator_maps_backtest_error_with_retryable_false():
    exc = BacktestServiceError(
        ErrorCode.INVALID_PARAMETER, "Unknown strategy 'nope'. Choose: rsi",
        strategy="nope", retryable=False,
    )
    env = exception_to_envelope(exc)
    assert is_error(env)
    assert env["error"]["code"] == "INVALID_PARAMETER"
    assert env["error"]["retryable"] is False


def test_translator_carries_partial_data_folds():
    folds = [{"fold": 1, "insufficient_data": True}]
    env = exception_to_envelope(
        BacktestServiceError(
            ErrorCode.PARTIAL_DATA, "Every test window is shorter than warmup",
            folds=folds, retryable=False,
        )
    )
    assert is_error(env)
    assert env["error"]["code"] == "PARTIAL_DATA"
    assert env["error"]["folds"] == folds


def test_translator_maps_unexpected_to_internal_error_with_context():
    env = exception_to_envelope(ValueError("boom"), context="backtest_strategy")
    assert env["error"]["code"] == "INTERNAL_ERROR"
    assert env["error"]["retryable"] is False
    assert "backtest_strategy" in env["error"]["message"]


# ── tool boundaries: every failure mode returns an envelope ────────────────────

@pytest.mark.parametrize("raiser,expected_code", [
    (_boom_backtest, "UPSTREAM_ERROR"),
    (_boom_invalid, "INVALID_PARAMETER"),
    (_boom_unexpected, "INTERNAL_ERROR"),
])
def test_backtest_strategy_never_leaks_raw_exceptions(monkeypatch, raiser, expected_code):
    monkeypatch.setattr(server, "run_backtest", raiser)
    result = server.backtest_strategy(symbol="AAPL", strategy="rsi")
    assert is_error(result)
    assert result["error"]["code"] == expected_code
    assert "retryable" in result["error"]


@pytest.mark.parametrize("raiser,expected_code", [
    (_boom_backtest, "UPSTREAM_ERROR"),
    (_boom_invalid, "INVALID_PARAMETER"),
    (_boom_unexpected, "INTERNAL_ERROR"),
])
def test_compare_strategies_never_leaks_raw_exceptions(monkeypatch, raiser, expected_code):
    monkeypatch.setattr(server, "_compare_strategies", raiser)
    result = server.compare_strategies(symbol="AAPL")
    assert is_error(result)
    assert result["error"]["code"] == expected_code
    assert "retryable" in result["error"]


@pytest.mark.parametrize("raiser,expected_code", [
    (_boom_backtest, "UPSTREAM_ERROR"),
    (_boom_invalid, "INVALID_PARAMETER"),
    (_boom_unexpected, "INTERNAL_ERROR"),
])
def test_walk_forward_never_leaks_raw_exceptions(monkeypatch, raiser, expected_code):
    monkeypatch.setattr(server, "walk_forward_backtest", raiser)
    result = server.walk_forward_backtest_strategy(symbol="AAPL", strategy="rsi")
    assert is_error(result)
    assert result["error"]["code"] == expected_code
    assert "retryable" in result["error"]


# ── service entry guards raise typed errors ────────────────────────────────────

def test_run_backtest_unknown_strategy_is_typed():
    from tradingview_mcp.core.services import backtest_service
    with pytest.raises(BacktestServiceError) as exc_info:
        backtest_service.run_backtest("AAPL", "nope")
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER
    assert exc_info.value.to_envelope()["error"]["retryable"] is False


def test_run_backtest_fetch_failure_is_retryable_upstream_error(monkeypatch):
    from tradingview_mcp.core.services import backtest_service

    def down(*args, **kwargs):
        raise TimeoutError("yahoo is having a moment")

    monkeypatch.setattr(backtest_service, "_fetch_ohlcv", down)
    with pytest.raises(BacktestServiceError) as exc_info:
        backtest_service.run_backtest("AAPL", "rsi")
    assert exc_info.value.code == ErrorCode.UPSTREAM_ERROR
    assert exc_info.value.to_envelope()["error"]["retryable"] is True


def test_run_backtest_short_history_is_no_data(monkeypatch):
    from tradingview_mcp.core.services import backtest_service
    monkeypatch.setattr(
        backtest_service, "_fetch_ohlcv",
        lambda *a, **k: [{"date": "2024-01-01", "open": 1.0, "high": 1.0,
                          "low": 1.0, "close": 1.0}],
    )
    with pytest.raises(BacktestServiceError) as exc_info:
        backtest_service.run_backtest("AAPL", "rsi", period="1mo")
    assert exc_info.value.code == ErrorCode.NO_DATA


def test_walk_forward_bad_n_splits_is_typed():
    from tradingview_mcp.core.services import backtest_service
    with pytest.raises(BacktestServiceError) as exc_info:
        backtest_service.walk_forward_backtest("AAPL", "rsi", n_splits=99)
    assert exc_info.value.code == ErrorCode.INVALID_PARAMETER
