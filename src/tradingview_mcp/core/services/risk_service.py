"""
Risk & Position Sizing Service — money management math for investors.

Why this exists: technical analysis tells you WHAT to buy, this service tells
you HOW MUCH. A great setup with the wrong size is still a losing strategy.
Covers:
  - Position sizing from account size + risk budget + stop distance
  - Kelly Criterion for optimal bet fraction
  - R-multiple / risk-reward calculator
  - Historical correlation matrix between assets
  - Value at Risk (VaR) — historical + parametric

Pure math except for VaR/correlation, which need price history. We fetch
that from Yahoo's chart endpoint directly (same as yahoo_finance_service)
to keep the dependency footprint zero.

All functions return error dicts on bad input rather than raising, so the
MCP layer can surface them to the user verbatim.
"""
from __future__ import annotations

import json
import math
import statistics
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.proxy_manager import build_opener_with_proxy

_TIMEOUT = 12
_UA = "tradingview-mcp/0.7.1"
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"


# ── Helpers: price history fetch ──────────────────────────────────────────────

def _fetch_closes(symbol: str, period: str = "6mo", interval: str = "1d") -> list[float]:
    url = f"{_CHART}/{symbol}?interval={interval}&range={period}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    opener = build_opener_with_proxy(_UA)
    with opener.open(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    result = data["chart"]["result"][0]
    raw = result["indicators"]["quote"][0]["close"]
    return [c for c in raw if c is not None]


def _returns(closes: list[float]) -> list[float]:
    """Daily log returns from a close series."""
    out: list[float] = []
    for i in range(1, len(closes)):
        prev, cur = closes[i - 1], closes[i]
        if prev <= 0 or cur <= 0:
            continue
        out.append(math.log(cur / prev))
    return out


# ── Position sizing ───────────────────────────────────────────────────────────

def position_size(
    account_size: float,
    risk_pct: float,
    entry: float,
    stop: float,
    asset_price_currency: str = "USD",
) -> dict:
    """How many units to buy given account size, max-risk %, and stop distance.

    The classic 1-2% rule made explicit:
      risk_dollars = account_size * risk_pct/100
      units = risk_dollars / |entry - stop|

    Args:
        account_size: Total trading capital
        risk_pct: % of account willing to lose if stop hits (typically 0.5-2)
        entry: Planned entry price
        stop: Planned stop-loss price (below entry for long, above for short)
        asset_price_currency: Display currency

    Returns:
        Recommended unit count, total position value, exposure %, and a
        warning if exposure exceeds 25% (over-concentration).
    """
    if account_size <= 0:
        return {"error": "account_size must be positive"}
    if risk_pct <= 0 or risk_pct > 100:
        return {"error": "risk_pct must be in (0, 100]"}
    if entry <= 0 or stop <= 0:
        return {"error": "entry and stop must be positive"}
    if entry == stop:
        return {"error": "entry and stop cannot be equal — no defined risk"}

    direction = "LONG" if stop < entry else "SHORT"
    risk_per_unit = abs(entry - stop)
    risk_dollars = account_size * (risk_pct / 100)
    units = risk_dollars / risk_per_unit
    position_value = units * entry
    exposure_pct = position_value / account_size * 100

    warnings: list[str] = []
    if exposure_pct > 100:
        warnings.append(
            f"Exposure {exposure_pct:.0f}% of account — requires leverage. "
            "Consider widening stop or reducing risk_pct."
        )
    elif exposure_pct > 25:
        warnings.append(
            f"Exposure {exposure_pct:.0f}% concentrates significant capital "
            "in a single position. Diversification suffers."
        )

    stop_distance_pct = risk_per_unit / entry * 100
    if stop_distance_pct < 0.5:
        warnings.append("Stop very tight (<0.5%) — noise may stop you out prematurely.")
    elif stop_distance_pct > 20:
        warnings.append("Stop very wide (>20%) — questionable risk/reward unless catalyst-driven.")

    return {
        "direction": direction,
        "account_size": account_size,
        "risk_pct": risk_pct,
        "risk_dollars": round(risk_dollars, 2),
        "entry": entry,
        "stop": stop,
        "risk_per_unit": round(risk_per_unit, 4),
        "stop_distance_pct": round(stop_distance_pct, 2),
        "units_to_buy": round(units, 4),
        "position_value": round(position_value, 2),
        "exposure_pct_of_account": round(exposure_pct, 2),
        "currency": asset_price_currency,
        "warnings": warnings,
    }


# ── Risk / Reward ─────────────────────────────────────────────────────────────

def risk_reward(entry: float, stop: float, target: float) -> dict:
    """R-multiple calculator: how many R's of profit per R of risk.

    Pro traders won't take a trade below 2R; institutional swing setups
    target 3R+. Below 1R means you risk more than you stand to make —
    a structural negative-edge bet that no win rate can save.
    """
    if entry <= 0 or stop <= 0 or target <= 0:
        return {"error": "entry, stop, target must all be positive"}

    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk == 0:
        return {"error": "entry equals stop — undefined risk"}

    r_multiple = reward / risk
    direction = "LONG" if target > entry else "SHORT"

    # Sanity check: target should be on the opposite side of entry from stop
    if direction == "LONG" and stop > entry:
        return {"error": "for LONG (target > entry), stop must be below entry"}
    if direction == "SHORT" and stop < entry:
        return {"error": "for SHORT (target < entry), stop must be above entry"}

    if r_multiple >= 3:
        grade = "EXCELLENT"
        note = "3R+ — institutional-grade setup; tolerates low win rate."
    elif r_multiple >= 2:
        grade = "GOOD"
        note = "2-3R — solid risk/reward; viable with >40% win rate."
    elif r_multiple >= 1:
        grade = "MARGINAL"
        note = "1-2R — needs >50% win rate to be profitable after costs."
    else:
        grade = "POOR"
        note = "<1R — risking more than you stand to win. Skip or restructure."

    breakeven_winrate_pct = round(1 / (1 + r_multiple) * 100, 1)

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_per_unit": round(risk, 4),
        "reward_per_unit": round(reward, 4),
        "r_multiple": round(r_multiple, 2),
        "grade": grade,
        "note": note,
        "breakeven_winrate_pct": breakeven_winrate_pct,
    }


# ── Kelly Criterion ───────────────────────────────────────────────────────────

def kelly_criterion(
    win_rate_pct: float,
    win_loss_ratio: float,
    capital: float = 10000.0,
    kelly_fraction: float = 0.5,
) -> dict:
    """Kelly bet sizing: optimal % of capital to risk per trade.

    Formula:  f* = W - (1 - W) / R     where W = win rate, R = avg_win/avg_loss

    Full Kelly is mathematically optimal but emotionally unbearable —
    drawdowns can be 50%+. Most pros use Half Kelly (0.5x) or Quarter Kelly.

    Args:
        win_rate_pct: Historical win rate, e.g. 55 for 55%
        win_loss_ratio: Average win size / average loss size (e.g. 1.5)
        capital: Account size
        kelly_fraction: Multiplier on full Kelly (0.25 = quarter, 0.5 = half)
    """
    if not 0 < win_rate_pct < 100:
        return {"error": "win_rate_pct must be in (0, 100)"}
    if win_loss_ratio <= 0:
        return {"error": "win_loss_ratio must be positive"}
    if capital <= 0:
        return {"error": "capital must be positive"}
    if not 0 < kelly_fraction <= 1:
        return {"error": "kelly_fraction must be in (0, 1]"}

    w = win_rate_pct / 100
    full_kelly = w - (1 - w) / win_loss_ratio
    applied = full_kelly * kelly_fraction

    if full_kelly <= 0:
        return {
            "win_rate_pct": win_rate_pct,
            "win_loss_ratio": win_loss_ratio,
            "full_kelly_pct": round(full_kelly * 100, 2),
            "verdict": "NEGATIVE_EDGE",
            "note": (
                "Kelly is negative — this strategy has no edge. "
                "Better to not trade than to trade smaller."
            ),
        }

    bet_dollars = capital * applied if applied > 0 else 0

    if full_kelly > 0.25:
        risk_note = "Full Kelly > 25% — extreme variance, use fractional Kelly."
    elif full_kelly > 0.10:
        risk_note = "Full Kelly in normal range. Half Kelly recommended for stability."
    else:
        risk_note = "Modest edge — even Full Kelly is small. Fractional sizing is fine."

    return {
        "win_rate_pct": win_rate_pct,
        "win_loss_ratio": win_loss_ratio,
        "full_kelly_pct": round(full_kelly * 100, 2),
        "applied_kelly_pct": round(applied * 100, 2),
        "kelly_fraction_used": kelly_fraction,
        "capital": capital,
        "recommended_bet_dollars": round(bet_dollars, 2),
        "verdict": "POSITIVE_EDGE",
        "risk_note": risk_note,
    }


# ── Correlation matrix ────────────────────────────────────────────────────────

def correlation_matrix(symbols: list[str], period: str = "6mo") -> dict:
    """Pairwise correlation of daily returns. Diversification check.

    > 0.7 — highly correlated (these positions move as one)
    0.3–0.7 — moderately correlated
    < 0.3 — meaningfully diversified
    < 0  — hedged / negatively correlated
    """
    symbols = [s.upper().strip() for s in symbols if s and s.strip()][:8]
    if len(symbols) < 2:
        return {"error": "at least 2 symbols required"}

    returns_by_symbol: dict[str, list[float]] = {}
    fetch_errors: dict[str, str] = {}
    for s in symbols:
        try:
            closes = _fetch_closes(s, period=period)
            if len(closes) < 20:
                fetch_errors[s] = f"insufficient history ({len(closes)} closes)"
                continue
            returns_by_symbol[s] = _returns(closes)
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            fetch_errors[s] = f"{type(e).__name__}: {e}"

    valid_symbols = list(returns_by_symbol.keys())
    if len(valid_symbols) < 2:
        return {"error": "could not fetch enough symbols", "fetch_errors": fetch_errors}

    # Align lengths — trim each to the shortest series so indices match
    min_len = min(len(r) for r in returns_by_symbol.values())
    aligned = {s: r[-min_len:] for s, r in returns_by_symbol.items()}

    matrix: dict[str, dict[str, float]] = {}
    notable: list[dict] = []
    for a in valid_symbols:
        matrix[a] = {}
        for b in valid_symbols:
            if a == b:
                matrix[a][b] = 1.0
                continue
            try:
                corr = statistics.correlation(aligned[a], aligned[b])
            except statistics.StatisticsError:
                corr = 0.0
            matrix[a][b] = round(corr, 3)

    # Surface notable pairs (only one direction, not both A→B and B→A)
    seen = set()
    for a in valid_symbols:
        for b in valid_symbols:
            if a == b or (b, a) in seen:
                continue
            seen.add((a, b))
            c = matrix[a][b]
            if c > 0.7:
                notable.append({"pair": f"{a}/{b}", "correlation": c, "note": "highly correlated — limited diversification"})
            elif c < -0.3:
                notable.append({"pair": f"{a}/{b}", "correlation": c, "note": "negatively correlated — natural hedge"})

    return {
        "symbols": valid_symbols,
        "period": period,
        "matrix": matrix,
        "notable_pairs": notable,
        "fetch_errors": fetch_errors,
        "source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Value at Risk ─────────────────────────────────────────────────────────────

def value_at_risk(
    symbol: str,
    position_value: float,
    period: str = "6mo",
    confidence: float = 0.95,
    horizon_days: int = 1,
) -> dict:
    """Historical + parametric VaR for a single position.

    Historical VaR: empirical percentile of past returns (no normality assumption).
    Parametric VaR: assumes returns ~ Normal(mean, std) — faster, riskier on fat tails.

    Args:
        symbol: Yahoo ticker
        position_value: Current $ value of the position
        period: History window for return distribution
        confidence: 0.95 → 95% VaR, 0.99 → 99% VaR
        horizon_days: Loss horizon (we scale by sqrt(t) for parametric)
    """
    if position_value <= 0:
        return {"error": "position_value must be positive"}
    if not 0.5 <= confidence < 1:
        return {"error": "confidence must be in [0.5, 1)"}
    if horizon_days < 1:
        return {"error": "horizon_days must be >= 1"}

    try:
        closes = _fetch_closes(symbol, period=period)
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        return {"symbol": symbol.upper(), "error": f"{type(e).__name__}: {e}"}

    if len(closes) < 30:
        return {"symbol": symbol.upper(), "error": f"insufficient history ({len(closes)} closes)"}

    returns = _returns(closes)
    if not returns:
        return {"symbol": symbol.upper(), "error": "no usable returns"}

    sorted_returns = sorted(returns)
    percentile_idx = max(0, int((1 - confidence) * len(sorted_returns)) - 1)
    hist_var_return = sorted_returns[percentile_idx]
    hist_var_dollars = position_value * (math.exp(hist_var_return) - 1)

    # Parametric VaR (Cornish-Fisher / normal assumption — quick approximation)
    mean = statistics.fmean(returns)
    std = statistics.stdev(returns) if len(returns) > 1 else 0.0
    # Inverse normal CDF approximation for common confidence levels
    z = {0.90: -1.282, 0.95: -1.645, 0.975: -1.960, 0.99: -2.326}.get(
        round(confidence, 3), -1.645
    )
    horizon_scale = math.sqrt(horizon_days)
    param_var_return = mean * horizon_days + z * std * horizon_scale
    param_var_dollars = position_value * (math.exp(param_var_return) - 1)

    # Expected shortfall — mean loss beyond VaR (the "if it gets bad" number)
    tail = sorted_returns[: percentile_idx + 1]
    es_return = statistics.fmean(tail) if tail else hist_var_return
    es_dollars = position_value * (math.exp(es_return) - 1)

    return {
        "symbol": symbol.upper(),
        "position_value": position_value,
        "period": period,
        "confidence_level": confidence,
        "horizon_days": horizon_days,
        "historical_var": {
            "loss_pct": round(hist_var_return * 100, 2),
            "loss_dollars": round(hist_var_dollars, 2),
            "interpretation": (
                f"On a typical day at {confidence*100:.0f}% confidence, "
                f"the worst loss observed historically was ${abs(round(hist_var_dollars, 2)):,.2f}"
            ),
        },
        "parametric_var": {
            "loss_pct": round(param_var_return * 100, 2),
            "loss_dollars": round(param_var_dollars, 2),
            "annualized_volatility_pct": round(std * math.sqrt(252) * 100, 2),
        },
        "expected_shortfall": {
            "loss_pct": round(es_return * 100, 2),
            "loss_dollars": round(es_dollars, 2),
            "interpretation": "Average loss in the worst-case scenarios beyond VaR",
        },
        "sample_size": len(returns),
        "source": "Yahoo Finance",
    }
