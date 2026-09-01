"""
Smart-money / banker-fund proxy indicators.

Volume-and-momentum decompositions in the spirit of the popular TradingView
"banker fund" family (MCDX, blackcat L3 fund-flow oscillators, smart-money
scripts). These are ORIGINAL implementations of the publicly documented
formula shapes — not copies of any closed-source script (MCDX Plus, LOKEN
etc. are proprietary; their exact parameters are unpublished). Every formula
used here is stated explicitly in its docstring so results are reproducible.

Honesty note (surfaced to callers in every payload): these indicators infer
"institutional" behaviour purely from price/volume statistics. They are NOT
actual institutional-flow data. For EGX, the exchange publishes real daily
investor-type flows (Egyptians/Arabs/Foreigners, institutions vs retail) —
that dataset is the genuine hot-money signal and a candidate future
integration; these proxies are the best that OHLCV alone can do.

Data source: Yahoo Finance daily/hourly OHLCV via the backtest service's
fetcher. EGX symbols map to Yahoo's ``.CA`` suffix (COMI -> COMI.CA).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tradingview_mcp.core.errors import ErrorCode, make_error
from tradingview_mcp.core.services.backtest_service import _fetch_ohlcv
from tradingview_mcp.core.services.indicators_calc import calc_ema, calc_rsi

_DISCLAIMER = (
    "Price/volume-derived proxy for institutional activity — not actual "
    "fund-flow data. Not investment advice."
)

_VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y"}

# Minimum bars each computation needs to say anything meaningful.
_MIN_BARS = 40


def yahoo_symbol_for(symbol: str, exchange: str) -> str:
    """Map an exchange-local ticker to its Yahoo Finance symbol.

    EGX trades on Yahoo under the ``.CA`` (Cairo) suffix; BIST under ``.IS``.
    Crypto and US tickers pass through unchanged. Symbols that already carry
    a Yahoo suffix or index prefix are left alone.
    """
    s = (symbol or "").strip().upper()
    if not s or "." in s or s.startswith("^") or "-" in s or "=" in s:
        return s
    ex = (exchange or "").strip().lower()
    suffix = {"egx": ".CA", "bist": ".IS", "tadawul": ".SR", "tasi": ".SR"}.get(ex)
    if suffix:
        return f"{s}{suffix}"
    return s


# ── MCDX-style banker / hot-money / retail decomposition ─────────────────────

def compute_mcdx(candles: List[dict]) -> Dict[str, Any]:
    """RSI-horizon decomposition in the style of the public MCDX indicator.

    Formula (explicit — this is our documented variant, 0..20 scale each):
        banker    = clamp((RSI(close, 50) - 40) * 1.5, 0, 20)
        hot_money = clamp((RSI(close, 40) - 30) * 1.5, 0, 20)
        retail    = clamp((RSI(close, 14) - 30) * 1.5, 0, 20)

    Interpretation: slow-horizon RSI strength that persists (banker) reflects
    sustained buying pressure that fast horizons (retail) can't fake; a rising
    banker bar with flat/falling retail is the classic "smart accumulation"
    read. All three at the cap means the move is crowded.
    """
    closes = [c["close"] for c in candles]

    def series(period: int, floor: float) -> List[Optional[float]]:
        rsi = calc_rsi(closes, period)
        return [
            None if r is None else round(max(0.0, min(20.0, (r - floor) * 1.5)), 2)
            for r in rsi
        ]

    banker = series(50, 40.0)
    hot = series(40, 30.0)
    retail = series(14, 30.0)

    def last(vals):
        return next((v for v in reversed(vals) if v is not None), None)

    def slope(vals, n=5):
        pts = [v for v in vals if v is not None][-n:]
        return round(pts[-1] - pts[0], 2) if len(pts) >= 2 else None

    b, h, r = last(banker), last(hot), last(retail)
    b_slope = slope(banker)

    if b is None:
        signal = "INSUFFICIENT_DATA"
    elif b >= 10 and (b_slope or 0) > 0 and (r is None or b > r):
        signal = "BANKER_ACCUMULATING"
    elif b >= 15 and r is not None and r >= 15:
        signal = "CROWDED"
    elif b <= 2 and (r or 0) >= 10:
        signal = "RETAIL_ONLY"
    elif (b_slope or 0) < -3:
        signal = "BANKER_DISTRIBUTING"
    else:
        signal = "NEUTRAL"

    return {
        "banker": b, "hot_money": h, "retail": r,
        "banker_slope_5bar": b_slope,
        "signal": signal,
        "series_tail": {
            "banker": banker[-10:], "hot_money": hot[-10:], "retail": retail[-10:],
        },
    }


# ── Banker fund-flow oscillator (blackcat-L3 style) ──────────────────────────

def compute_banker_fund_oscillator(candles: List[dict]) -> Dict[str, Any]:
    """EMA-smoothed stochastic of the weighted typical price, 0..100.

    Formula (explicit):
        typ       = (2*close + high + low + open) / 5
        raw       = (typ - lowest(low, 34)) / (highest(high, 34) - lowest(low, 34)) * 100
        oscillator = EMA(raw, 13)

    States (in the convention of the public "banker fund flow" oscillators):
        < 20            → oversold / banker entry zone
        cross above 20  → BANKER_ENTRY
        20-50 rising    → ACCUMULATION
        50-80           → TREND / banker holding
        > 80            → OVERHEATED (retail chase zone)
        cross below 80  → BANKER_EXIT warning
    """
    n = len(candles)
    lookback, smooth = 34, 13
    typ = [(2 * c["close"] + c["high"] + c["low"] + c["open"]) / 5 for c in candles]
    lows = [c["low"] for c in candles]
    highs = [c["high"] for c in candles]

    raw: List[Optional[float]] = [None] * n
    for i in range(lookback - 1, n):
        lo = min(lows[i - lookback + 1 : i + 1])
        hi = max(highs[i - lookback + 1 : i + 1])
        raw[i] = ((typ[i] - lo) / (hi - lo) * 100) if hi > lo else 50.0

    valid = [(i, v) for i, v in enumerate(raw) if v is not None]
    osc: List[Optional[float]] = [None] * n
    if valid:
        smoothed = calc_ema([v for _, v in valid], smooth)
        for (i, _), s in zip(valid, smoothed):
            osc[i] = round(s, 2) if s is not None else None

    cur = next((v for v in reversed(osc) if v is not None), None)
    prev_vals = [v for v in osc if v is not None]
    prev = prev_vals[-2] if len(prev_vals) >= 2 else None

    if cur is None:
        state = "INSUFFICIENT_DATA"
    elif prev is not None and prev < 20 <= cur:
        state = "BANKER_ENTRY"
    elif prev is not None and prev >= 80 > cur:
        state = "BANKER_EXIT"
    elif cur < 20:
        state = "OVERSOLD"
    elif cur > 80:
        state = "OVERHEATED"
    elif prev is not None and cur > prev and cur < 50:
        state = "ACCUMULATION"
    elif cur >= 50:
        state = "TREND"
    else:
        state = "COOLING"

    return {
        "oscillator": cur,
        "previous": prev,
        "state": state,
        "series_tail": osc[-10:],
    }


# ── Smart-money composite (volume-flow evidence, 0..100) ─────────────────────

def compute_smart_money_composite(candles: List[dict]) -> Dict[str, Any]:
    """Composite accumulation/distribution score from four volume-flow reads.

    Components (each mapped to 0..100, equally weighted):
      - CMF(20):  Chaikin Money Flow — close-location-weighted volume share.
      - MFI(14):  Money Flow Index — volume-weighted RSI of typical price.
      - OBV 20-bar trend: net on-balance volume over 20 bars, normalised by
        total 20-bar volume.
      - Up/down volume balance (20 bars): volume on up-closes vs down-closes.

    Verdicts: >=70 STRONG_ACCUMULATION, >=58 ACCUMULATION, <=30
    STRONG_DISTRIBUTION, <=42 DISTRIBUTION, else NEUTRAL.
    """
    n = len(candles)
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c["volume"] or 0 for c in candles]
    win = min(20, n)

    # CMF(20)
    mfv = []
    for i in range(n):
        rng = highs[i] - lows[i]
        mult = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / rng if rng > 0 else 0.0
        mfv.append(mult * vols[i])
    vol_sum = sum(vols[-win:])
    cmf = (sum(mfv[-win:]) / vol_sum) if vol_sum > 0 else 0.0

    # MFI(14)
    mfi_win = min(14, n - 1)
    pos_flow = neg_flow = 0.0
    for i in range(n - mfi_win, n):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        tp_prev = (highs[i - 1] + lows[i - 1] + closes[i - 1]) / 3
        flow = tp * vols[i]
        if tp > tp_prev:
            pos_flow += flow
        elif tp < tp_prev:
            neg_flow += flow
    mfi = 100.0 * pos_flow / (pos_flow + neg_flow) if (pos_flow + neg_flow) > 0 else 50.0

    # OBV 20-bar net trend, normalised to [-1, 1] by total volume.
    obv_net = 0.0
    for i in range(n - win + 1, n):
        if closes[i] > closes[i - 1]:
            obv_net += vols[i]
        elif closes[i] < closes[i - 1]:
            obv_net -= vols[i]
    obv_norm = (obv_net / vol_sum) if vol_sum > 0 else 0.0

    # Up/down volume balance.
    up_vol = sum(vols[i] for i in range(n - win + 1, n) if closes[i] > closes[i - 1])
    dn_vol = sum(vols[i] for i in range(n - win + 1, n) if closes[i] < closes[i - 1])
    updn = up_vol / (up_vol + dn_vol) if (up_vol + dn_vol) > 0 else 0.5

    components = {
        "cmf_20": round(cmf, 4),
        "mfi_14": round(mfi, 2),
        "obv_trend_20": round(obv_norm, 4),
        "up_down_volume_ratio": round(updn, 4),
    }
    scores = {
        "cmf_20": (cmf + 1) / 2 * 100,        # CMF in [-1, 1]
        "mfi_14": mfi,                         # already 0..100
        "obv_trend_20": (obv_norm + 1) / 2 * 100,
        "up_down_volume_ratio": updn * 100,
    }
    score = round(sum(scores.values()) / len(scores), 1)

    if score >= 70:
        verdict = "STRONG_ACCUMULATION"
    elif score >= 58:
        verdict = "ACCUMULATION"
    elif score <= 30:
        verdict = "STRONG_DISTRIBUTION"
    elif score <= 42:
        verdict = "DISTRIBUTION"
    else:
        verdict = "NEUTRAL"

    return {"score": score, "verdict": verdict, "components": components}


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_smart_money(
    symbol: str,
    exchange: str = "EGX",
    period: str = "6mo",
    interval: str = "1d",
) -> dict:
    """Full smart-money read for one symbol: MCDX-style decomposition,
    banker fund-flow oscillator, and the volume-flow composite."""
    period = (period or "6mo").lower().strip()
    if period not in _VALID_PERIODS:
        return make_error(
            ErrorCode.INVALID_PARAMETER,
            f"Invalid period {period!r}.", valid_periods=sorted(_VALID_PERIODS),
        )
    if interval not in ("1d", "1h"):
        return make_error(ErrorCode.INVALID_PARAMETER, "interval must be 1d or 1h")

    ysym = yahoo_symbol_for(symbol, exchange)
    try:
        candles = _fetch_ohlcv(ysym, period, interval)
    except Exception as e:
        return make_error(
            ErrorCode.UPSTREAM_ERROR,
            f"Failed to fetch history for {ysym!r}: {e}",
            yahoo_symbol=ysym, retryable=True,
        )
    if len(candles) < _MIN_BARS:
        return make_error(
            ErrorCode.NO_DATA,
            f"Only {len(candles)} bars for {ysym!r}; need >= {_MIN_BARS}. "
            f"Try a longer period.",
            yahoo_symbol=ysym,
        )

    mcdx = compute_mcdx(candles)
    osc = compute_banker_fund_oscillator(candles)
    composite = compute_smart_money_composite(candles)

    # Agreement read across the three families.
    bullish_votes = sum([
        mcdx["signal"] in ("BANKER_ACCUMULATING",),
        osc["state"] in ("BANKER_ENTRY", "ACCUMULATION", "TREND"),
        composite["verdict"] in ("ACCUMULATION", "STRONG_ACCUMULATION"),
    ])
    bearish_votes = sum([
        mcdx["signal"] in ("BANKER_DISTRIBUTING", "RETAIL_ONLY"),
        osc["state"] in ("BANKER_EXIT", "OVERHEATED"),
        composite["verdict"] in ("DISTRIBUTION", "STRONG_DISTRIBUTION"),
    ])
    if bullish_votes >= 2 and bearish_votes == 0:
        consensus = "SMART_MONEY_IN"
    elif bearish_votes >= 2 and bullish_votes == 0:
        consensus = "SMART_MONEY_OUT"
    elif bullish_votes and bearish_votes:
        consensus = "MIXED"
    else:
        consensus = "NEUTRAL"

    return {
        "symbol": (symbol or "").upper(),
        "exchange": (exchange or "").upper(),
        "yahoo_symbol": ysym,
        "period": period,
        "interval": interval,
        "bars_analyzed": len(candles),
        "as_of": candles[-1]["date"],
        "last_close": candles[-1]["close"],
        "mcdx_style": mcdx,
        "banker_fund_oscillator": osc,
        "volume_flow_composite": composite,
        "consensus": {
            "read": consensus,
            "bullish_votes": bullish_votes,
            "bearish_votes": bearish_votes,
        },
        "methodology_note": _DISCLAIMER,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def scan_egx_smart_money(
    index: str = "EGX30",
    limit: int = 10,
    period: str = "6mo",
    min_score: float = 0.0,
) -> dict:
    """Rank an EGX index's constituents by smart-money evidence.

    Fetches Yahoo history per constituent (bounded thread pool — Yahoo has no
    batch OHLCV endpoint) and ranks by the volume-flow composite score, with
    the MCDX-style and oscillator reads attached per row.
    """
    from tradingview_mcp.core.data.egx_indices import EGX_INDICES

    key = (index or "EGX30").upper().strip()
    if key not in EGX_INDICES:
        return make_error(
            ErrorCode.INVALID_PARAMETER,
            f"Unknown EGX index {index!r}.", valid_indices=sorted(EGX_INDICES),
        )
    # get_symbols() returns EGX:-prefixed tickers; Yahoo wants the bare name.
    symbols = [s.split(":", 1)[-1] for s in EGX_INDICES[key]["get_symbols"]()]
    limit = max(1, min(int(limit), 50))

    rows: List[dict] = []
    skipped: List[dict] = []

    def one(sym: str) -> Optional[dict]:
        result = analyze_smart_money(sym, "EGX", period, "1d")
        if "error" in result:
            skipped.append({"symbol": sym, "reason": result["error"]["message"][:120]})
            return None
        return {
            "symbol": sym,
            "last_close": result["last_close"],
            "as_of": result["as_of"],
            "composite_score": result["volume_flow_composite"]["score"],
            "composite_verdict": result["volume_flow_composite"]["verdict"],
            "banker": result["mcdx_style"]["banker"],
            "banker_signal": result["mcdx_style"]["signal"],
            "oscillator": result["banker_fund_oscillator"]["oscillator"],
            "oscillator_state": result["banker_fund_oscillator"]["state"],
            "consensus": result["consensus"]["read"],
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(one, s) for s in symbols]
        for f in as_completed(futures):
            row = f.result()
            if row is not None and row["composite_score"] >= min_score:
                rows.append(row)

    rows.sort(key=lambda r: r["composite_score"], reverse=True)
    return {
        "index": key,
        "period": period,
        "constituents_scanned": len(symbols),
        "returned": min(limit, len(rows)),
        "skipped": skipped,
        "rows": rows[:limit],
        "methodology_note": _DISCLAIMER,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
