from __future__ import annotations
from typing import Dict, Optional, Tuple


def compute_change(open_price: float, close: float) -> float:
    return ((close - open_price) / open_price) * 100 if open_price else 0.0


def compute_bbw(sma: float, bb_upper: float, bb_lower: float) -> Optional[float]:
    if not sma:
        return None
    try:
        return (bb_upper - bb_lower) / sma
    except ZeroDivisionError:
        return None


def compute_bb_rating_signal(close: float, bb_upper: float, bb_middle: float, bb_lower: float) -> Tuple[int, str]:
    rating = 0
    if close > bb_upper:
        rating = 3
    elif close > bb_middle + ((bb_upper - bb_middle) / 2):
        rating = 2
    elif close > bb_middle:
        rating = 1
    elif close < bb_lower:
        rating = -3
    elif close < bb_middle - ((bb_middle - bb_lower) / 2):
        rating = -2
    elif close < bb_middle:
        rating = -1

    signal = "NEUTRAL"
    if rating >= 2:
        signal = "BUY"
    elif rating <= -2:
        signal = "SELL"
    return rating, signal


def compute_metrics(indicators: Dict) -> Optional[Dict]:
    try:
        open_price = indicators["open"]
        close = indicators["close"]
        sma = indicators["SMA20"]
        bb_upper = indicators["BB.upper"]
        bb_lower = indicators["BB.lower"]
        bb_middle = sma

        change = compute_change(open_price, close)
        bbw = compute_bbw(sma, bb_upper, bb_lower)
        rating, signal = compute_bb_rating_signal(close, bb_upper, bb_middle, bb_lower)

        return {
            "price": round(close, 4),
            "change": round(change, 3),
            "bbw": round(bbw, 4) if bbw is not None else None,
            "rating": rating,
            "signal": signal,
        }
    except (KeyError, TypeError):
        return None


def _safe_round(value, decimals: int = 4):
    """Round a value safely, returning None if the value is None or invalid."""
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def extract_extended_indicators(indicators: Dict) -> Dict:
    """Extract extended technical indicators from TradingView data.

    Returns a dict with RSI, OBV, SMA, EMA, ATR, MACD, Volume, Support/Resistance,
    Bollinger Bands, and market structure details.
    """
    close = indicators.get("close")
    open_price = indicators.get("open")
    high = indicators.get("high")
    low = indicators.get("low")
    volume = indicators.get("volume")

    # --- RSI ---
    rsi_value = indicators.get("RSI")
    rsi_signal = "Neutral"
    if rsi_value is not None:
        if rsi_value > 70:
            rsi_signal = "Overbought"
        elif rsi_value > 60:
            rsi_signal = "Bullish"
        elif rsi_value < 30:
            rsi_signal = "Oversold"
        elif rsi_value < 40:
            rsi_signal = "Bearish"

    rsi = {
        "value": _safe_round(rsi_value, 2),
        "signal": rsi_signal,
    }

    # --- OBV (On Balance Volume) ---
    obv_direction = None
    if volume is not None and open_price and close:
        obv_direction = "accumulation" if close > open_price else "distribution" if close < open_price else "neutral"

    obv = {
        "current_volume": _safe_round(volume, 0),
        "direction": obv_direction,
        "note": "OBV direction inferred from current candle (close vs open)",
    }

    # --- SMA (Simple Moving Average) ---
    sma10 = indicators.get("SMA10")
    sma20 = indicators.get("SMA20")
    sma30 = indicators.get("SMA30")
    sma50 = indicators.get("SMA50")
    sma100 = indicators.get("SMA100")
    sma200 = indicators.get("SMA200")

    sma_data = {
        "sma10": _safe_round(sma10, 4),
        "sma20": _safe_round(sma20, 4),
        "sma30": _safe_round(sma30, 4),
        "sma50": _safe_round(sma50, 4),
        "sma100": _safe_round(sma100, 4),
        "sma200": _safe_round(sma200, 4),
    }

    # SMA trend signals
    sma_signals = []
    if close and sma50:
        if close > sma50:
            sma_signals.append("Price above SMA50 (bullish)")
        else:
            sma_signals.append("Price below SMA50 (bearish)")
    if close and sma200:
        if close > sma200:
            sma_signals.append("Price above SMA200 (long-term bullish)")
        else:
            sma_signals.append("Price below SMA200 (long-term bearish)")
    if sma50 and sma200:
        if sma50 > sma200:
            sma_signals.append("Golden Cross (SMA50 > SMA200)")
        else:
            sma_signals.append("Death Cross (SMA50 < SMA200)")

    sma_data["signals"] = sma_signals

    # --- EMA (Exponential Moving Average) ---
    ema9 = indicators.get("EMA9")
    ema10 = indicators.get("EMA10")
    ema20 = indicators.get("EMA20")
    ema30 = indicators.get("EMA30")
    ema50 = indicators.get("EMA50")
    ema100 = indicators.get("EMA100")
    ema200 = indicators.get("EMA200")

    ema_data = {
        "ema9": _safe_round(ema9, 4),
        "ema10": _safe_round(ema10, 4),
        "ema20": _safe_round(ema20, 4),
        "ema30": _safe_round(ema30, 4),
        "ema50": _safe_round(ema50, 4),
        "ema100": _safe_round(ema100, 4),
        "ema200": _safe_round(ema200, 4),
    }

    # EMA trend signals
    ema_signals = []
    if close and ema20:
        if close > ema20:
            ema_signals.append("Price above EMA20 (short-term bullish)")
        else:
            ema_signals.append("Price below EMA20 (short-term bearish)")
    if close and ema50:
        if close > ema50:
            ema_signals.append("Price above EMA50 (mid-term bullish)")
        else:
            ema_signals.append("Price below EMA50 (mid-term bearish)")
    if close and ema200:
        if close > ema200:
            ema_signals.append("Price above EMA200 (long-term bullish)")
        else:
            ema_signals.append("Price below EMA200 (long-term bearish)")
    if ema50 and ema200:
        if ema50 > ema200:
            ema_signals.append("Golden Cross (EMA50 > EMA200)")
        else:
            ema_signals.append("Death Cross (EMA50 < EMA200)")
    if ema9 and ema20:
        if ema9 > ema20:
            ema_signals.append("Fast EMA bullish (EMA9 > EMA20)")
        else:
            ema_signals.append("Fast EMA bearish (EMA9 < EMA20)")

    ema_data["signals"] = ema_signals

    # --- ATR (Average True Range) ---
    atr_value = indicators.get("ATR")
    atr_pct = None
    if atr_value is not None and close and close > 0:
        atr_pct = (atr_value / close) * 100

    atr = {
        "value": _safe_round(atr_value, 4),
        "percent_of_price": _safe_round(atr_pct, 2),
        "volatility": "High" if atr_pct and atr_pct > 3 else "Medium" if atr_pct and atr_pct > 1.5 else "Low",
    }

    # --- MACD ---
    macd_line = indicators.get("MACD.macd")
    macd_signal_line = indicators.get("MACD.signal")
    macd_histogram = None
    macd_crossover = "Neutral"
    if macd_line is not None and macd_signal_line is not None:
        macd_histogram = macd_line - macd_signal_line
        if macd_line > macd_signal_line:
            macd_crossover = "Bullish"
        elif macd_line < macd_signal_line:
            macd_crossover = "Bearish"

    macd = {
        "macd_line": _safe_round(macd_line, 6),
        "signal_line": _safe_round(macd_signal_line, 6),
        "histogram": _safe_round(macd_histogram, 6),
        "crossover": macd_crossover,
    }

    # --- Volume ---
    volume_sma20 = indicators.get("volume.SMA20")
    volume_ratio = None
    volume_signal = "Normal"
    if volume is not None and volume_sma20 and volume_sma20 > 0:
        volume_ratio = volume / volume_sma20
        if volume_ratio >= 3.0:
            volume_signal = "Very High"
        elif volume_ratio >= 2.0:
            volume_signal = "High"
        elif volume_ratio >= 1.5:
            volume_signal = "Above Average"
        elif volume_ratio < 0.5:
            volume_signal = "Very Low"
        elif volume_ratio < 0.8:
            volume_signal = "Below Average"

    volume_data = {
        "current": _safe_round(volume, 0),
        "average_20": _safe_round(volume_sma20, 0),
        "ratio": _safe_round(volume_ratio, 2),
        "signal": volume_signal,
    }

    # --- Bollinger Bands ---
    bb_upper = indicators.get("BB.upper")
    bb_lower = indicators.get("BB.lower")
    bb_middle = sma20  # BB middle = SMA20

    bb_data = {
        "upper": _safe_round(bb_upper, 4),
        "middle": _safe_round(bb_middle, 4),
        "lower": _safe_round(bb_lower, 4),
    }

    if bb_upper and bb_lower and bb_middle and bb_middle > 0:
        bbw = (bb_upper - bb_lower) / bb_middle
        bb_data["width"] = _safe_round(bbw, 4)
        bb_data["squeeze"] = bbw < 0.02
    else:
        bb_data["width"] = None
        bb_data["squeeze"] = False

    if close and bb_upper and bb_lower:
        if close > bb_upper:
            bb_data["position"] = "Above Upper Band"
        elif close < bb_lower:
            bb_data["position"] = "Below Lower Band"
        elif bb_middle and close > bb_middle:
            bb_data["position"] = "Upper Half"
        else:
            bb_data["position"] = "Lower Half"
    else:
        bb_data["position"] = "Unknown"

    # --- Support & Resistance (from Pivot Points) ---
    support_resistance = _extract_support_resistance(indicators, close)

    # --- Stochastic ---
    stoch_k = indicators.get("Stoch.K")
    stoch_d = indicators.get("Stoch.D")
    stoch_signal = "Neutral"
    if stoch_k is not None:
        if stoch_k > 80:
            stoch_signal = "Overbought"
        elif stoch_k < 20:
            stoch_signal = "Oversold"

    stochastic = {
        "k": _safe_round(stoch_k, 2),
        "d": _safe_round(stoch_d, 2),
        "signal": stoch_signal,
    }

    # --- ADX (Trend Strength) ---
    adx_value = indicators.get("ADX")
    adx = {
        "value": _safe_round(adx_value, 2),
        "trend_strength": "Strong Trend" if adx_value and adx_value > 25 else
                          "Weak/No Trend" if adx_value and adx_value < 20 else "Moderate",
    }

    # --- VWAP (if available) ---
    vwap_value = indicators.get("VWAP")
    vwap = None
    if vwap_value is not None:
        vwap = {
            "value": _safe_round(vwap_value, 4),
            "position": "Above VWAP (bullish)" if close and close > vwap_value else "Below VWAP (bearish)",
        }

    # --- CCI (Commodity Channel Index) ---
    cci_value = indicators.get("CCI20")
    cci_signal = "Neutral"
    if cci_value is not None:
        if cci_value > 100:
            cci_signal = "Overbought"
        elif cci_value > 0:
            cci_signal = "Bullish"
        elif cci_value < -100:
            cci_signal = "Oversold"
        elif cci_value < 0:
            cci_signal = "Bearish"

    cci = {
        "value": _safe_round(cci_value, 2),
        "signal": cci_signal,
    }

    # --- Williams %R ---
    wr_value = indicators.get("W.R")
    wr_signal = "Neutral"
    if wr_value is not None:
        if wr_value > -20:
            wr_signal = "Overbought"
        elif wr_value < -80:
            wr_signal = "Oversold"

    williams_r = {
        "value": _safe_round(wr_value, 2),
        "signal": wr_signal,
    }

    # --- Awesome Oscillator ---
    ao_value = indicators.get("AO")
    ao_prev = indicators.get("AO[1]")
    ao_signal = "Neutral"
    if ao_value is not None:
        if ao_value > 0:
            ao_signal = "Bullish"
            if ao_prev is not None and ao_value > ao_prev:
                ao_signal = "Bullish (Rising)"
        else:
            ao_signal = "Bearish"
            if ao_prev is not None and ao_value < ao_prev:
                ao_signal = "Bearish (Falling)"

    awesome_oscillator = {
        "value": _safe_round(ao_value, 4),
        "signal": ao_signal,
    }

    # --- Momentum ---
    mom_value = indicators.get("Mom")
    mom_prev = indicators.get("Mom[1]")
    mom_signal = "Neutral"
    if mom_value is not None:
        if mom_value > 0:
            mom_signal = "Bullish"
            if mom_prev is not None and mom_value > mom_prev:
                mom_signal = "Bullish (Accelerating)"
        else:
            mom_signal = "Bearish"
            if mom_prev is not None and mom_value < mom_prev:
                mom_signal = "Bearish (Accelerating)"

    momentum = {
        "value": _safe_round(mom_value, 4),
        "signal": mom_signal,
    }

    # --- Parabolic SAR ---
    psar_value = indicators.get("P.SAR")
    psar = {
        "value": _safe_round(psar_value, 4),
        "trend": "Bullish (price above SAR)" if close and psar_value and close > psar_value
                 else "Bearish (price below SAR)" if close and psar_value
                 else "Unknown",
    }

    # --- Ichimoku ---
    ichimoku_bline = indicators.get("Ichimoku.BLine")
    ichimoku = {
        "baseline": _safe_round(ichimoku_bline, 4),
        "position": "Above Baseline (bullish)" if close and ichimoku_bline and close > ichimoku_bline
                    else "Below Baseline (bearish)" if close and ichimoku_bline
                    else "Unknown",
    }

    # --- Stochastic RSI ---
    stoch_rsi_k = indicators.get("Stoch.RSI.K")
    stoch_rsi_signal = "Neutral"
    if stoch_rsi_k is not None:
        if stoch_rsi_k > 80:
            stoch_rsi_signal = "Overbought"
        elif stoch_rsi_k < 20:
            stoch_rsi_signal = "Oversold"

    stochastic_rsi = {
        "k": _safe_round(stoch_rsi_k, 2),
        "signal": stoch_rsi_signal,
    }

    # --- ADX Directional Movement (+DI / -DI) ---
    adx_plus_di = indicators.get("ADX+DI")
    adx_minus_di = indicators.get("ADX-DI")
    di_signal = "Neutral"
    if adx_plus_di is not None and adx_minus_di is not None:
        if adx_plus_di > adx_minus_di:
            di_signal = "Bullish (+DI > -DI)"
        else:
            di_signal = "Bearish (-DI > +DI)"

    adx["plus_di"] = _safe_round(adx_plus_di, 2)
    adx["minus_di"] = _safe_round(adx_minus_di, 2)
    adx["di_signal"] = di_signal

    # --- Hull Moving Average ---
    hull_ma = indicators.get("HullMA9")
    hull = {
        "value": _safe_round(hull_ma, 4),
        "position": "Above Hull MA (bullish)" if close and hull_ma and close > hull_ma
                    else "Below Hull MA (bearish)" if close and hull_ma
                    else "Unknown",
    }

    # --- VWMA (Volume Weighted Moving Average) ---
    vwma_value = indicators.get("VWMA")
    vwma = None
    if vwma_value is not None:
        vwma = {
            "value": _safe_round(vwma_value, 4),
            "position": "Above VWMA (bullish)" if close and close > vwma_value else "Below VWMA (bearish)",
        }

    # --- Ultimate Oscillator ---
    uo_value = indicators.get("UO")
    uo_signal = "Neutral"
    if uo_value is not None:
        if uo_value > 70:
            uo_signal = "Overbought"
        elif uo_value > 50:
            uo_signal = "Bullish"
        elif uo_value < 30:
            uo_signal = "Oversold"
        elif uo_value < 50:
            uo_signal = "Bearish"

    ultimate_oscillator = {
        "value": _safe_round(uo_value, 2),
        "signal": uo_signal,
    }

    # --- RSI Direction (rising or falling) ---
    rsi_prev = indicators.get("RSI[1]")
    if rsi_value is not None and rsi_prev is not None:
        rsi["direction"] = "Rising" if rsi_value > rsi_prev else "Falling" if rsi_value < rsi_prev else "Flat"
        rsi["previous"] = _safe_round(rsi_prev, 2)

    # --- TradingView Built-in Recommendations ---
    rec_all = indicators.get("Recommend.All")
    rec_ma = indicators.get("Recommend.MA")
    rec_other = indicators.get("Recommend.Other")

    def _rec_label(val):
        if val is None:
            return "Unknown"
        if val >= 0.5:
            return "Strong Buy"
        if val > 0.1:
            return "Buy"
        if val <= -0.5:
            return "Strong Sell"
        if val < -0.1:
            return "Sell"
        return "Neutral"

    tv_recommendation = {
        "overall": _safe_round(rec_all, 3),
        "overall_signal": _rec_label(rec_all),
        "moving_averages": _safe_round(rec_ma, 3),
        "ma_signal": _rec_label(rec_ma),
        "oscillators": _safe_round(rec_other, 3),
        "oscillators_signal": _rec_label(rec_other),
    }

    # --- Market Structure ---
    structure = _detect_market_structure(indicators, close, open_price, high, low)

    result = {
        "rsi": rsi,
        "obv": obv,
        "sma": sma_data,
        "ema": ema_data,
        "atr": atr,
        "macd": macd,
        "volume": volume_data,
        "bollinger_bands": bb_data,
        "support_resistance": support_resistance,
        "stochastic": stochastic,
        "stochastic_rsi": stochastic_rsi,
        "adx": adx,
        "cci": cci,
        "williams_r": williams_r,
        "awesome_oscillator": awesome_oscillator,
        "momentum": momentum,
        "parabolic_sar": psar,
        "ichimoku": ichimoku,
        "hull_ma": hull,
        "ultimate_oscillator": ultimate_oscillator,
        "tv_recommendation": tv_recommendation,
        "market_structure": structure,
    }

    if vwap is not None:
        result["vwap"] = vwap
    if vwma is not None:
        result["vwma"] = vwma

    return result


def _extract_support_resistance(indicators: Dict, close) -> Dict:
    """Extract support and resistance levels from pivot points."""
    # Classic pivot points
    pivot = indicators.get("Pivot.M.Classic.Middle")
    r1 = indicators.get("Pivot.M.Classic.R1")
    r2 = indicators.get("Pivot.M.Classic.R2")
    r3 = indicators.get("Pivot.M.Classic.R3")
    s1 = indicators.get("Pivot.M.Classic.S1")
    s2 = indicators.get("Pivot.M.Classic.S2")
    s3 = indicators.get("Pivot.M.Classic.S3")

    levels = {
        "pivot": _safe_round(pivot, 4),
        "resistance_1": _safe_round(r1, 4),
        "resistance_2": _safe_round(r2, 4),
        "resistance_3": _safe_round(r3, 4),
        "support_1": _safe_round(s1, 4),
        "support_2": _safe_round(s2, 4),
        "support_3": _safe_round(s3, 4),
    }

    # Determine nearest support and resistance
    if close:
        resistance_levels = [(v, k) for k, v in levels.items()
                             if v is not None and "resistance" in k and v > close]
        support_levels = [(v, k) for k, v in levels.items()
                          if v is not None and "support" in k and v < close]

        if resistance_levels:
            nearest_r = min(resistance_levels, key=lambda x: x[0])
            levels["nearest_resistance"] = nearest_r[0]
            levels["distance_to_resistance_pct"] = _safe_round(
                ((nearest_r[0] - close) / close) * 100, 2
            )
        if support_levels:
            nearest_s = max(support_levels, key=lambda x: x[0])
            levels["nearest_support"] = nearest_s[0]
            levels["distance_to_support_pct"] = _safe_round(
                ((close - nearest_s[0]) / close) * 100, 2
            )

    return levels


def _detect_market_structure(indicators: Dict, close, open_price, high, low) -> Dict:
    """Detect market structure: trend direction, momentum alignment, candle characteristics."""
    ema20 = indicators.get("EMA20")
    ema50 = indicators.get("EMA50")
    ema200 = indicators.get("EMA200")
    rsi = indicators.get("RSI")
    adx = indicators.get("ADX")
    macd_line = indicators.get("MACD.macd")
    macd_signal = indicators.get("MACD.signal")

    # --- Trend Direction ---
    trend_score = 0  # -3 (strong bearish) to +3 (strong bullish)
    trend_signals = []

    if close and ema20:
        if close > ema20:
            trend_score += 1
        else:
            trend_score -= 1

    if close and ema50:
        if close > ema50:
            trend_score += 1
        else:
            trend_score -= 1

    if close and ema200:
        if close > ema200:
            trend_score += 1
            trend_signals.append("Above 200 EMA (bullish structure)")
        else:
            trend_score -= 1
            trend_signals.append("Below 200 EMA (bearish structure)")

    if trend_score >= 2:
        trend = "Bullish"
    elif trend_score <= -2:
        trend = "Bearish"
    else:
        trend = "Neutral/Ranging"

    # --- Momentum Alignment ---
    momentum_aligned = False
    if rsi is not None and macd_line is not None and macd_signal is not None:
        bullish_momentum = rsi > 50 and macd_line > macd_signal
        bearish_momentum = rsi < 50 and macd_line < macd_signal
        momentum_aligned = (trend == "Bullish" and bullish_momentum) or \
                           (trend == "Bearish" and bearish_momentum)

    # --- Candle Analysis ---
    candle = {}
    if all(v is not None for v in [open_price, close, high, low]) and high != low:
        body = abs(close - open_price)
        total_range = high - low
        body_ratio = body / total_range if total_range > 0 else 0

        candle["type"] = "Bullish" if close > open_price else "Bearish" if close < open_price else "Doji"
        candle["body_ratio"] = _safe_round(body_ratio, 2)
        candle["strength"] = "Strong" if body_ratio > 0.7 else "Moderate" if body_ratio > 0.4 else "Weak"

        # Upper/lower wick analysis
        if close >= open_price:
            upper_wick = high - close
            lower_wick = open_price - low
        else:
            upper_wick = high - open_price
            lower_wick = close - low
        candle["upper_wick_pct"] = _safe_round((upper_wick / total_range) * 100, 1) if total_range > 0 else 0
        candle["lower_wick_pct"] = _safe_round((lower_wick / total_range) * 100, 1) if total_range > 0 else 0

    # --- Trend Strength ---
    trend_strength = "Weak"
    if adx is not None:
        if adx > 40:
            trend_strength = "Very Strong"
        elif adx > 25:
            trend_strength = "Strong"
        elif adx > 20:
            trend_strength = "Moderate"

    return {
        "trend": trend,
        "trend_score": trend_score,
        "trend_strength": trend_strength,
        "momentum_aligned": momentum_aligned,
        "trend_signals": trend_signals,
        "candle": candle,
    }


def analyze_timeframe_context(indicators: Dict, timeframe: str) -> Dict:
    """Provide timeframe-specific analysis based on the trading strategy framework.

    Different timeframes serve different purposes:
    - 1W: Big picture trend, institutional direction
    - 1D: Swing trading setups (days to weeks)
    - 4h: Refinement within daily trend
    - 1h: Precise entry timing
    - 15m/5m: Execution and scalping
    """
    close = indicators.get("close")
    rsi = indicators.get("RSI")
    ema20 = indicators.get("EMA20")
    ema50 = indicators.get("EMA50")
    ema100 = indicators.get("EMA100")
    ema200 = indicators.get("EMA200")
    macd_line = indicators.get("MACD.macd")
    macd_signal = indicators.get("MACD.signal")
    adx = indicators.get("ADX")
    volume = indicators.get("volume")
    volume_sma20 = indicators.get("volume.SMA20")
    vwap = indicators.get("VWAP")

    # Determine bias
    bias = "Neutral"
    bias_reasons = []

    if timeframe in ("1W", "1M"):
        # Weekly: 200 EMA + 100 EMA for trend, MACD for momentum, RSI > 50 = bullish
        key_indicators = ["200 EMA", "100 EMA", "MACD", "RSI(14)"]
        if close and ema200:
            if close > ema200:
                bias = "Bullish"
                bias_reasons.append(f"Price ({_safe_round(close,2)}) above 200 EMA ({_safe_round(ema200,2)})")
            else:
                bias = "Bearish"
                bias_reasons.append(f"Price ({_safe_round(close,2)}) below 200 EMA ({_safe_round(ema200,2)})")
        if rsi is not None:
            if rsi > 50:
                bias_reasons.append(f"RSI {_safe_round(rsi,1)} above 50 (bullish bias)")
            else:
                bias_reasons.append(f"RSI {_safe_round(rsi,1)} below 50 (bearish bias)")
        if macd_line is not None and macd_signal is not None:
            if macd_line > macd_signal:
                bias_reasons.append("MACD bullish (momentum shift up)")
            else:
                bias_reasons.append("MACD bearish (momentum shift down)")
        advice = "Weekly sets your BIAS, not entries. Only look for buy setups in uptrends."

    elif timeframe == "1D":
        # Daily: 50 EMA + 200 EMA, RSI pullbacks (40-60 zone), Volume, MACD
        key_indicators = ["50 EMA", "200 EMA", "RSI(14)", "Volume", "MACD"]
        if close and ema50 and ema200:
            if ema50 > ema200:
                bias = "Bullish"
                bias_reasons.append("Golden Cross: EMA50 > EMA200")
            else:
                bias = "Bearish"
                bias_reasons.append("Death Cross: EMA50 < EMA200")
        if rsi is not None:
            if 40 <= rsi <= 60:
                bias_reasons.append(f"RSI {_safe_round(rsi,1)} in pullback zone (40-60) - good entry area")
            elif rsi > 70:
                bias_reasons.append(f"RSI {_safe_round(rsi,1)} overbought - avoid new longs")
            elif rsi < 30:
                bias_reasons.append(f"RSI {_safe_round(rsi,1)} oversold - potential bounce")
        if volume and volume_sma20 and volume_sma20 > 0:
            ratio = volume / volume_sma20
            if ratio >= 1.5:
                bias_reasons.append(f"Volume {ratio:.1f}x above average (breakout confirmation)")
        advice = "Trade pullbacks in trend (not extremes). Look for confluence: EMA + support + RSI."

    elif timeframe == "4h":
        # 4H: 20 EMA + 50 EMA, RSI, MACD, trendlines
        key_indicators = ["20 EMA", "50 EMA", "RSI(14)", "MACD"]
        if close and ema20 and ema50:
            if close > ema20 and ema20 > ema50:
                bias = "Bullish"
                bias_reasons.append("Price > EMA20 > EMA50 (bullish alignment)")
            elif close < ema20 and ema20 < ema50:
                bias = "Bearish"
                bias_reasons.append("Price < EMA20 < EMA50 (bearish alignment)")
            else:
                bias_reasons.append("EMAs not aligned - ranging/transitioning")
        if macd_line is not None and macd_signal is not None:
            if macd_line > macd_signal:
                bias_reasons.append("MACD bullish - early reversal signal")
            else:
                bias_reasons.append("MACD bearish - early reversal signal")
        advice = "Align with daily direction. Enter on pullbacks or breakouts."

    elif timeframe in ("1h", "60"):
        # 1H: 20 EMA dynamic S/R, RSI 9-14, Volume spikes, VWAP
        key_indicators = ["20 EMA", "RSI(9-14)", "Volume spikes", "VWAP"]
        if close and ema20:
            if close > ema20:
                bias = "Bullish"
                bias_reasons.append(f"Price above 20 EMA (dynamic support at {_safe_round(ema20,2)})")
            else:
                bias = "Bearish"
                bias_reasons.append(f"Price below 20 EMA (dynamic resistance at {_safe_round(ema20,2)})")
        if volume and volume_sma20 and volume_sma20 > 0:
            ratio = volume / volume_sma20
            if ratio >= 2.0:
                bias_reasons.append(f"Volume spike: {ratio:.1f}x (breakout confirmation)")
        if vwap is not None and close:
            if close > vwap:
                bias_reasons.append(f"Above VWAP ({_safe_round(vwap,2)}) - institutional bullish")
            else:
                bias_reasons.append(f"Below VWAP ({_safe_round(vwap,2)}) - institutional bearish")
        advice = "Look for trend continuation setups. Avoid trading against higher TF trend."

    else:
        # 15m/5m: VWAP, 20 EMA + 9 EMA, RSI 7-9, Volume
        key_indicators = ["VWAP", "9 EMA", "20 EMA", "RSI(7-9)", "Volume"]
        ema9 = indicators.get("EMA9")
        if close and ema9 and ema20:
            if ema9 > ema20:
                bias = "Bullish"
                bias_reasons.append("Fast EMA9 > EMA20 (short-term bullish)")
            else:
                bias = "Bearish"
                bias_reasons.append("Fast EMA9 < EMA20 (short-term bearish)")
        if vwap is not None and close:
            if close > vwap:
                bias_reasons.append(f"Above VWAP ({_safe_round(vwap,2)}) - institutional level bullish")
            else:
                bias_reasons.append(f"Below VWAP ({_safe_round(vwap,2)}) - institutional level bearish")
        advice = "Only enter when aligned with 1H & 4H. Use tight stop losses."

    return {
        "timeframe": timeframe,
        "bias": bias,
        "bias_reasons": bias_reasons,
        "key_indicators_for_timeframe": key_indicators,
        "advice": advice,
    }


# ---------------------------------------------------------------------------
# LAYER A — Stock Quality & Momentum Score (100 pts)
# Answers: "Which stocks deserve attention?"
# ---------------------------------------------------------------------------

def compute_stock_score(indicators: Dict, change_pct_rank: Optional[float] = None, currency: str = "EGP") -> Optional[Dict]:
    """Compute a 100-point composite stock score for ranking.

    Sections:
      A. Trend & Momentum  — 50 pts (EMA structure, RSI, MACD, relative perf)
      B. Confirmation       — 20 pts (Volume, ADX)
      C. Risk-Adjusted      — 15 pts (ATR volatility, drawdown proxy)
      D. Fundamental Overlay— 15 pts (TV recommendation as proxy)

    Args:
        indicators: TradingView indicator dict.
        change_pct_rank: Percentile rank (0.0–1.0) of this stock's change
                         among the scanned universe. 0.0 = worst, 1.0 = best.
                         If None, relative performance section is skipped.

    Returns dict with score, breakdown, grade, signals, penalties. None if no data.
    """
    close = indicators.get("close")
    open_price = indicators.get("open")
    if not close or not open_price:
        return None

    breakdown = {}
    signals = []
    penalties = []
    total = 0

    # ── A. Trend & Momentum — 50 pts ──────────────────────────────────────

    # A1. EMA Trend Structure — 15 pts
    ema20 = indicators.get("EMA20")
    ema50 = indicators.get("EMA50")
    ema200 = indicators.get("EMA200")

    if ema20 and ema50 and ema200:
        if close > ema20 > ema50 > ema200:
            ema_pts = 15
            signals.append("Perfect EMA alignment (Price>20>50>200)")
        elif close > ema20 > ema50:
            ema_pts = 10
            signals.append("EMA bullish (Price>20>50, 50<=200)")
        elif close > ema20:
            ema_pts = 5
            signals.append("Price above EMA20 only")
        else:
            ema_pts = 0
    elif ema20 and close > ema20:
        ema_pts = 5
    else:
        ema_pts = 0
    breakdown["ema_trend"] = ema_pts
    total += ema_pts

    # A2. RSI Strength Zone — 10 pts
    rsi = indicators.get("RSI")
    rsi_pts = 0
    if rsi is not None:
        if 55 <= rsi <= 70:
            rsi_pts = 10
            signals.append(f"RSI {rsi:.0f} in optimal zone (55-70)")
        elif 50 <= rsi < 55:
            rsi_pts = 7
        elif 70 < rsi <= 75:
            rsi_pts = 5
            signals.append(f"RSI {rsi:.0f} slightly elevated")
        elif 45 <= rsi < 50:
            rsi_pts = 3
        else:
            rsi_pts = 0
    breakdown["rsi"] = rsi_pts
    total += rsi_pts

    # A3. MACD Confirmation — 10 pts
    macd_line = indicators.get("MACD.macd")
    macd_signal = indicators.get("MACD.signal")
    macd_pts = 0
    if macd_line is not None and macd_signal is not None:
        histogram = macd_line - macd_signal
        if macd_line > macd_signal and histogram > 0:
            macd_pts = 10
            signals.append("MACD bullish + histogram rising")
        elif macd_line > macd_signal:
            macd_pts = 7
            signals.append("MACD bullish crossover")
        elif histogram > 0:
            macd_pts = 4
        else:
            macd_pts = 0
    breakdown["macd"] = macd_pts
    total += macd_pts

    # A4. Relative Price Performance — 15 pts
    perf_pts = 0
    if change_pct_rank is not None:
        if change_pct_rank >= 0.90:
            perf_pts = 15
            signals.append("Top 10% price performer")
        elif change_pct_rank >= 0.75:
            perf_pts = 12
            signals.append("Top 25% price performer")
        elif change_pct_rank >= 0.60:
            perf_pts = 8
        elif change_pct_rank >= 0.40:
            perf_pts = 4
        else:
            perf_pts = 0
    breakdown["relative_performance"] = perf_pts
    total += perf_pts

    # ── B. Confirmation — 20 pts ──────────────────────────────────────────

    # B5. Volume Confirmation — 10 pts
    volume = indicators.get("volume")
    vol_sma20 = indicators.get("volume.SMA20")
    vol_pts = 0
    vol_ratio = None
    if volume and vol_sma20 and vol_sma20 > 0:
        vol_ratio = volume / vol_sma20
        if vol_ratio >= 1.5:
            vol_pts = 10
            signals.append(f"Volume {vol_ratio:.1f}x above avg (strong participation)")
        elif vol_ratio >= 1.2:
            vol_pts = 7
        elif vol_ratio >= 1.0:
            vol_pts = 4
        else:
            vol_pts = 0
    breakdown["volume_confirmation"] = vol_pts
    total += vol_pts

    # B6. ADX Trend Strength — 10 pts
    adx = indicators.get("ADX")
    adx_plus = indicators.get("ADX+DI")
    adx_minus = indicators.get("ADX-DI")
    adx_pts = 0
    if adx is not None:
        if adx >= 30:
            adx_pts = 10
            signals.append(f"Strong trend (ADX {adx:.0f})")
        elif 25 <= adx < 30:
            adx_pts = 8
        elif 20 <= adx < 25:
            adx_pts = 5
        else:
            adx_pts = 0
    breakdown["adx"] = adx_pts
    total += adx_pts

    # ── C. Risk-Adjusted Technical Quality — 15 pts ───────────────────────

    # C7. Volatility Control (ATR%) — 10 pts
    atr_val = indicators.get("ATR")
    atr_pct = (atr_val / close) * 100 if atr_val and close > 0 else None
    vol_ctrl_pts = 0
    if atr_pct is not None:
        if 1.0 <= atr_pct <= 3.0:
            vol_ctrl_pts = 10
            signals.append(f"ATR% {atr_pct:.1f}% (healthy volatility)")
        elif 3.0 < atr_pct <= 4.5:
            vol_ctrl_pts = 7
        elif 4.5 < atr_pct <= 6.0:
            vol_ctrl_pts = 4
        else:
            vol_ctrl_pts = 0
            if atr_pct > 6.0:
                signals.append(f"ATR% {atr_pct:.1f}% (very volatile)")
    breakdown["volatility_control"] = vol_ctrl_pts
    total += vol_ctrl_pts

    # C8. Drawdown Stability proxy — 5 pts
    # We don't have 60-day history, so approximate via:
    #   distance from 200-EMA and BB width as stability proxies
    stab_pts = 0
    sma200 = indicators.get("SMA200")
    bb_upper = indicators.get("BB.upper")
    bb_lower = indicators.get("BB.lower")
    sma20 = indicators.get("SMA20")
    if sma200 and close and sma200 > 0:
        dist_200 = ((close - sma200) / sma200) * 100
        if 0 < dist_200 <= 20:
            stab_pts += 3  # Healthy distance above SMA200
        elif dist_200 > 40:
            stab_pts += 0  # Overextended
        elif dist_200 > 20:
            stab_pts += 1
    if bb_upper and bb_lower and sma20 and sma20 > 0:
        bbw = (bb_upper - bb_lower) / sma20
        if bbw < 0.08:
            stab_pts += 2  # Tight bands = stability
        elif bbw < 0.15:
            stab_pts += 1
    stab_pts = min(5, stab_pts)
    breakdown["drawdown_stability"] = stab_pts
    total += stab_pts

    # ── D. Fundamental Overlay — 15 pts ───────────────────────────────────
    # TradingView doesn't provide EPS/revenue directly.
    # Use TradingView's built-in recommendation as a proxy for quality.

    rec_all = indicators.get("Recommend.All")
    rec_ma = indicators.get("Recommend.MA")
    rec_other = indicators.get("Recommend.Other")

    # D9. Growth Quality proxy (TV overall recommendation) — 10 pts
    growth_pts = 0
    if rec_all is not None:
        if rec_all >= 0.5:
            growth_pts = 10
            signals.append("TV Strong Buy recommendation")
        elif rec_all >= 0.1:
            growth_pts = 7
        elif rec_all >= -0.1:
            growth_pts = 4
        else:
            growth_pts = 0
    breakdown["growth_quality"] = growth_pts
    total += growth_pts

    # D10. Profitability proxy (MA + Oscillator agreement) — 5 pts
    prof_pts = 0
    if rec_ma is not None and rec_other is not None:
        if rec_ma > 0.1 and rec_other > 0.1:
            prof_pts = 5
        elif rec_ma > 0 or rec_other > 0:
            prof_pts = 3
        else:
            prof_pts = 0
    breakdown["profitability_quality"] = prof_pts
    total += prof_pts

    # ── Bonus / Penalty ───────────────────────────────────────────────────

    bonus = 0

    # Bonus: Volume surge with positive price = breakout candidate
    change_pct = ((close - open_price) / open_price) * 100
    if vol_ratio and vol_ratio >= 1.5 and change_pct > 2.0:
        bonus += 3
        signals.append("Breakout candidate (volume + price surge)")

    # Penalty: Price below EMA200
    if ema200 and close < ema200:
        bonus -= 10
        penalties.append("Price below EMA200 (-10)")

    # Penalty: RSI > 78 (extreme overbought)
    if rsi is not None and rsi > 78:
        bonus -= 5
        penalties.append(f"RSI {rsi:.0f} extreme overbought (-5)")

    # Penalty: Very low relative volume (today vs own average)
    if vol_ratio is not None and vol_ratio < 0.5:
        bonus -= 10
        penalties.append("Very low relative volume (-10)")

    # ── Liquidity Assessment ──────────────────────────────────────────────
    avg_vol = vol_sma20 if vol_sma20 and vol_sma20 > 0 else (volume if volume else None)
    avg_value_20d = (avg_vol * close) if avg_vol and close else None
    liquidity_ok = True       # passes hard gate for Strong/Elite
    liquidity_cap = None      # hard grade cap (None = no cap)
    liquidity_warnings = []

    # Layer 1: Absolute volume penalties
    if avg_vol is not None:
        if avg_vol < 10_000:
            bonus -= 20
            penalties.append(f"Extremely low volume {avg_vol:,.0f} shares/day (-20)")
            liquidity_ok = False
            liquidity_cap = "Avoid"
            liquidity_warnings.append("near-zero daily activity")
        elif avg_vol < 50_000:
            bonus -= 10
            penalties.append(f"Low volume {avg_vol:,.0f} shares/day (-10)")
            liquidity_ok = False
            liquidity_cap = "Watchlist"
            liquidity_warnings.append("thin daily volume")
        elif avg_vol < 100_000:
            bonus -= 5
            penalties.append(f"Below-average volume {avg_vol:,.0f} shares/day (-5)")

    # Layer 2: Traded value penalty (volume * price)
    # Catches stocks with high share count but low price, or vice versa
    # USD-denominated stocks use ~50x lower thresholds (1 USD ≈ 50 EGP)
    if currency.upper() == "USD":
        val_floor, val_low, val_modest = 2_000, 10_000, 20_000
    else:
        val_floor, val_low, val_modest = 100_000, 500_000, 1_000_000
    ccy = currency.upper()

    if avg_value_20d is not None:
        if avg_value_20d < val_floor:
            bonus -= 15
            penalties.append(f"Very low traded value {avg_value_20d:,.0f} {ccy}/day (-15)")
            liquidity_ok = False
            if liquidity_cap != "Avoid":
                liquidity_cap = "Avoid"
            liquidity_warnings.append("negligible monetary turnover")
        elif avg_value_20d < val_low:
            bonus -= 8
            penalties.append(f"Low traded value {avg_value_20d:,.0f} {ccy}/day (-8)")
            liquidity_ok = False
            if liquidity_cap is None:
                liquidity_cap = "Watchlist"
            liquidity_warnings.append("low monetary turnover")
        elif avg_value_20d < val_modest:
            bonus -= 3
            penalties.append(f"Modest traded value {avg_value_20d:,.0f} {ccy}/day (-3)")

    # Layer 3: Zero current volume — today is dead
    if volume is not None and volume == 0:
        bonus -= 10
        penalties.append("Zero volume today — no trading activity (-10)")
        liquidity_ok = False
        liquidity_cap = "Avoid"
        liquidity_warnings.append("zero trades today")

    # Penalty: ADX weak + bearish DI
    if adx is not None and adx < 15 and adx_plus and adx_minus and adx_minus > adx_plus:
        bonus -= 5
        penalties.append("Weak bearish trend structure (-5)")

    total = max(0, min(100, total + bonus))

    # ── Grade (with hard liquidity gate) ──────────────────────────────────
    grade_order = ["Avoid", "Watchlist", "Strong", "Elite"]
    if total >= 85:
        grade = "Elite"
    elif total >= 70:
        grade = "Strong"
    elif total >= 55:
        grade = "Watchlist"
    else:
        grade = "Avoid"

    # Hard cap: illiquid stocks cannot be graded above their liquidity cap
    if liquidity_cap and grade_order.index(grade) > grade_order.index(liquidity_cap):
        original_grade = grade
        grade = liquidity_cap
        penalties.append(f"Grade capped {original_grade} → {grade} (insufficient liquidity)")

    # Trend state
    if ema20 and ema50 and ema200:
        if close > ema20 > ema50 > ema200:
            trend_state = "Strong Uptrend"
        elif close > ema50 > ema200:
            trend_state = "Uptrend"
        elif close > ema200:
            trend_state = "Weak Uptrend"
        elif close < ema20 < ema50 < ema200:
            trend_state = "Strong Downtrend"
        else:
            trend_state = "Transitioning"
    else:
        trend_state = "Unknown"

    return {
        "score": total,
        "grade": grade,
        "trend_state": trend_state,
        "change_pct": _safe_round(change_pct, 2),
        "breakdown": breakdown,
        "signals": signals,
        "penalties": penalties,
        "liquidity": {
            "avg_volume_20d": round(avg_vol) if avg_vol else 0,
            "avg_value_20d": round(avg_value_20d) if avg_value_20d else 0,
            "current_volume": round(volume) if volume else 0,
            "liquidity_ok": liquidity_ok,
            "warnings": liquidity_warnings,
        },
    }


# Keep old function as alias for backward compatibility
def compute_momentum_score(indicators: Dict) -> Optional[Dict]:
    """Legacy wrapper — calls compute_stock_score without cross-sectional rank."""
    result = compute_stock_score(indicators)
    if result:
        result["momentum_grade"] = result.pop("grade", "")
        result["momentum_score"] = result.pop("score", 0)
    return result


# ---------------------------------------------------------------------------
# LAYER B — Trade Setup Engine
# Answers: "How do I enter, target, and control risk?"
# ---------------------------------------------------------------------------

def compute_trade_setup(indicators: Dict) -> Optional[Dict]:
    """Generate entry points, stop-loss, targets, and S/R levels.

    Only call this for stocks that pass the stock score threshold (>=70).
    """
    close = indicators.get("close")
    high = indicators.get("high")
    low = indicators.get("low")
    atr = indicators.get("ATR")
    ema20 = indicators.get("EMA20")
    ema50 = indicators.get("EMA50")
    ema200 = indicators.get("EMA200")

    if not close or not atr or atr <= 0:
        return None

    # ── Support & Resistance Levels ───────────────────────────────────────
    # Collect candidate levels from multiple sources
    support_candidates = []
    resistance_candidates = []

    # Pivot points
    for key_prefix in ("Pivot.M.Classic", "Pivot.M.Fibonacci"):
        for i in range(1, 4):
            s_val = indicators.get(f"{key_prefix}.S{i}")
            r_val = indicators.get(f"{key_prefix}.R{i}")
            if s_val and s_val < close:
                support_candidates.append(s_val)
            if r_val and r_val > close:
                resistance_candidates.append(r_val)

    # EMAs as dynamic S/R
    for ema_val in [ema20, ema50, ema200]:
        if ema_val and ema_val < close:
            support_candidates.append(ema_val)
        elif ema_val and ema_val > close:
            resistance_candidates.append(ema_val)

    # BB bands
    bb_lower = indicators.get("BB.lower")
    bb_upper = indicators.get("BB.upper")
    if bb_lower and bb_lower < close:
        support_candidates.append(bb_lower)
    if bb_upper and bb_upper > close:
        resistance_candidates.append(bb_upper)

    # Parabolic SAR
    psar = indicators.get("P.SAR")
    if psar and psar < close:
        support_candidates.append(psar)

    # Deduplicate and sort
    supports = sorted([x for x in set(_safe_round(s, 2) for s in support_candidates if s) if x is not None], reverse=True)[:3]
    resistances = sorted([x for x in set(_safe_round(r, 2) for r in resistance_candidates if r) if x is not None])[:3]

    # ── Entry Points ──────────────────────────────────────────────────────

    # Breakout entry: above nearest resistance
    breakout_entry = None
    if resistances:
        breakout_entry = resistances[0]

    # Pullback entry: near EMA20 or nearest support
    pullback_entry = None
    if ema20 and ema20 < close:
        pullback_entry = _safe_round(ema20, 2)
    elif supports:
        pullback_entry = supports[0]

    setup_types = []
    if breakout_entry:
        setup_types.append("breakout")
    if pullback_entry:
        setup_types.append("pullback")

    # ── Stop-Loss ─────────────────────────────────────────────────────────
    # Tighter of: below nearest support by 0.5×ATR, or entry - 1.5×ATR

    atr_stop = _safe_round(close - 1.5 * atr, 2)
    support_stop = None
    if supports:
        support_stop = _safe_round(supports[0] - 0.5 * atr, 2)

    if support_stop and atr_stop:
        stop_loss = max(support_stop, atr_stop)  # Tighter of the two
    elif support_stop:
        stop_loss = support_stop
    else:
        stop_loss = atr_stop

    # Validate stop isn't unrealistically tight (<0.5% from close) or wide (>10%)
    stop_pct = ((close - stop_loss) / close) * 100 if stop_loss else None
    if stop_pct is not None and stop_pct < 0.5:
        stop_loss = _safe_round(close - 1.0 * atr, 2)
        stop_pct = ((close - stop_loss) / close) * 100

    # ── Targets ───────────────────────────────────────────────────────────
    target_1 = resistances[0] if len(resistances) >= 1 else _safe_round(close + 1.5 * atr, 2)
    target_2 = resistances[1] if len(resistances) >= 2 else _safe_round(close + 3.0 * atr, 2)

    # ── Risk/Reward Ratios ────────────────────────────────────────────────
    risk = close - stop_loss if stop_loss else None
    rr_1 = _safe_round((target_1 - close) / risk, 1) if risk and risk > 0 else None
    rr_2 = _safe_round((target_2 - close) / risk, 1) if risk and risk > 0 else None

    # R:R quality
    rr_quality = "Weak"
    if rr_2 and rr_2 >= 2.5:
        rr_quality = "Strong"
    elif rr_2 and rr_2 >= 2.0:
        rr_quality = "Good"
    elif rr_2 and rr_2 >= 1.5:
        rr_quality = "Acceptable"

    return {
        "setup_types": setup_types,
        "entry_points": {
            "breakout_entry": breakout_entry,
            "pullback_entry": pullback_entry,
        },
        "stop_loss": stop_loss,
        "stop_distance_pct": _safe_round(stop_pct, 2),
        "targets": {
            "target_1": target_1,
            "target_2": target_2,
        },
        "risk_reward": {
            "to_target_1": rr_1,
            "to_target_2": rr_2,
            "quality": rr_quality,
        },
        "supports": supports,
        "resistances": resistances,
    }


# ---------------------------------------------------------------------------
# LAYER C — Trade Quality Score (100 pts)
# Answers: "Is this setup actually tradable?"
# ---------------------------------------------------------------------------

def compute_trade_quality(indicators: Dict, stock_score: int, trade_setup: Dict) -> Dict:
    """Score the trade setup quality out of 100.

    Sections:
      Structure Quality  — 30 pts
      Risk/Reward        — 30 pts
      Volume Confirmation— 20 pts
      Stop Placement     — 10 pts
      Liquidity          — 10 pts
    """
    close = indicators.get("close")
    ema20 = indicators.get("EMA20")
    ema50 = indicators.get("EMA50")
    ema200 = indicators.get("EMA200")
    adx = indicators.get("ADX")
    volume = indicators.get("volume")
    vol_sma20 = indicators.get("volume.SMA20")

    total = 0
    breakdown = {}
    notes = []

    # ── Structure Quality — 30 pts ────────────────────────────────────────
    struct_pts = 0
    # Clean trend
    if ema20 and ema50 and ema200 and close:
        if close > ema20 > ema50 > ema200:
            struct_pts += 15
            notes.append("Clean uptrend structure")
        elif close > ema50:
            struct_pts += 8
    # Strong trend (ADX)
    if adx and adx > 25:
        struct_pts += 10
    elif adx and adx > 20:
        struct_pts += 5
    # No messy overhead resistance (check if nearest R is far enough)
    resistances = trade_setup.get("resistances", [])
    if resistances and close:
        dist_to_r1 = ((resistances[0] - close) / close) * 100
        if dist_to_r1 > 3:
            struct_pts += 5
            notes.append(f"Room to run ({dist_to_r1:.1f}% to R1)")
        elif dist_to_r1 < 1:
            notes.append(f"Resistance very close ({dist_to_r1:.1f}%)")
    breakdown["structure_quality"] = min(30, struct_pts)
    total += breakdown["structure_quality"]

    # ── Risk/Reward — 30 pts ──────────────────────────────────────────────
    rr2 = trade_setup.get("risk_reward", {}).get("to_target_2")
    rr_pts = 0
    if rr2 is not None:
        if rr2 >= 2.5:
            rr_pts = 30
            notes.append(f"Excellent R:R {rr2:.1f}")
        elif rr2 >= 2.0:
            rr_pts = 24
        elif rr2 >= 1.5:
            rr_pts = 15
        else:
            rr_pts = 0
            notes.append(f"Poor R:R {rr2:.1f} - weak setup")
    breakdown["risk_reward"] = rr_pts
    total += rr_pts

    # ── Volume Confirmation — 20 pts ──────────────────────────────────────
    vol_pts = 0
    if volume and vol_sma20 and vol_sma20 > 0:
        ratio = volume / vol_sma20
        if ratio >= 1.5:
            vol_pts = 20
            notes.append(f"Strong volume participation ({ratio:.1f}x)")
        elif ratio >= 1.2:
            vol_pts = 14
        elif ratio >= 1.0:
            vol_pts = 8
        else:
            vol_pts = 0
    breakdown["volume_confirmation"] = vol_pts
    total += vol_pts

    # ── Stop Placement Quality — 10 pts ───────────────────────────────────
    stop_pct = trade_setup.get("stop_distance_pct")
    stop_pts = 0
    if stop_pct is not None:
        if 1.5 <= stop_pct <= 5.0:
            stop_pts = 10
            notes.append(f"Logical stop at {stop_pct:.1f}% below")
        elif 0.5 <= stop_pct < 1.5:
            stop_pts = 5
            notes.append("Stop might be too tight")
        elif 5.0 < stop_pct <= 8.0:
            stop_pts = 5
            notes.append("Wide stop — reduce position size")
        else:
            stop_pts = 0
            notes.append("Stop placement problematic")
    breakdown["stop_quality"] = stop_pts
    total += stop_pts

    # ── Liquidity — 10 pts ────────────────────────────────────────────────
    liq_pts = 0
    if volume and vol_sma20:
        # Use average volume as liquidity proxy
        if vol_sma20 >= 500000:
            liq_pts = 10
        elif vol_sma20 >= 100000:
            liq_pts = 7
        elif vol_sma20 >= 50000:
            liq_pts = 4
        else:
            liq_pts = 0
            notes.append("Low liquidity — harder to enter/exit")
    breakdown["liquidity"] = liq_pts
    total += liq_pts

    total = max(0, min(100, total))

    if total >= 80:
        quality = "High Quality Setup"
    elif total >= 65:
        quality = "Tradable"
    elif total >= 50:
        quality = "Weak Setup"
    else:
        quality = "Avoid Execution"

    return {
        "trade_quality_score": total,
        "quality": quality,
        "breakdown": breakdown,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Fibonacci Retracement Analysis
# ---------------------------------------------------------------------------

_FIB_RETRACEMENT_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
_FIB_EXTENSION_RATIOS = [1.272, 1.618, 2.618]


def detect_trend_for_fibonacci(
    close: float,
    swing_high: float,
    swing_low: float,
    ema50: Optional[float] = None,
    ema200: Optional[float] = None,
) -> Tuple[str, str]:
    """Determine trend direction for Fibonacci drawing.

    Returns (trend, reasoning) where trend is 'uptrend' or 'downtrend'.
    """
    midpoint = (swing_high + swing_low) / 2
    ema_bullish = ema50 is not None and ema200 is not None and ema50 > ema200
    ema_bearish = ema50 is not None and ema200 is not None and ema50 < ema200

    if close >= midpoint:
        trend = "uptrend"
        reason = f"Price ({close:.2f}) above midpoint ({midpoint:.2f})"
        if ema_bullish:
            reason += "; EMA50 > EMA200 confirms"
        elif ema_bearish:
            reason += "; note: EMA50 < EMA200 (mixed signal)"
    else:
        trend = "downtrend"
        reason = f"Price ({close:.2f}) below midpoint ({midpoint:.2f})"
        if ema_bearish:
            reason += "; EMA50 < EMA200 confirms"
        elif ema_bullish:
            reason += "; note: EMA50 > EMA200 (mixed signal)"

    return trend, reason


def compute_fibonacci_levels(
    swing_high: float, swing_low: float, trend: str
) -> Dict:
    """Calculate Fibonacci retracement and extension levels.

    For uptrend: 0% = swing_high (start), 100% = swing_low (full retrace).
    For downtrend: 0% = swing_low (start), 100% = swing_high (full retrace).
    """
    diff = swing_high - swing_low

    retracement = {}
    for ratio in _FIB_RETRACEMENT_RATIOS:
        if trend == "uptrend":
            price = swing_high - ratio * diff
        else:
            price = swing_low + ratio * diff
        retracement[str(ratio)] = _safe_round(price, 2)

    extensions = {}
    for ratio in _FIB_EXTENSION_RATIOS:
        if trend == "uptrend":
            price = swing_high + (ratio - 1.0) * diff
        else:
            price = swing_low - (ratio - 1.0) * diff
        extensions[str(ratio)] = _safe_round(price, 2)

    return {
        "swing_high": _safe_round(swing_high, 2),
        "swing_low": _safe_round(swing_low, 2),
        "trend": trend,
        "retracement_levels": retracement,
        "extension_levels": extensions,
    }


def analyze_fibonacci_position(close: float, fib_levels: Dict) -> Dict:
    """Analyze where the current price sits relative to Fibonacci levels."""
    retrace = fib_levels["retracement_levels"]
    # Build sorted list of (ratio_str, price) by price ascending
    sorted_levels = sorted(retrace.items(), key=lambda x: x[1])

    # Find current zone (between which two levels)
    current_zone = None
    for i in range(len(sorted_levels) - 1):
        lo_ratio, lo_price = sorted_levels[i]
        hi_ratio, hi_price = sorted_levels[i + 1]
        if lo_price <= close <= hi_price:
            current_zone = f"Between {lo_ratio} ({lo_price}) and {hi_ratio} ({hi_price})"
            break

    if current_zone is None:
        if close < sorted_levels[0][1]:
            current_zone = f"Below all levels (below {sorted_levels[0][0]} at {sorted_levels[0][1]})"
        else:
            current_zone = f"Above all levels (above {sorted_levels[-1][0]} at {sorted_levels[-1][1]})"

    # Nearest level
    nearest = min(sorted_levels, key=lambda x: abs(x[1] - close))
    nearest_dist_pct = _safe_round(((close - nearest[1]) / close) * 100, 2) if close else 0

    # Key zone detection
    key_zone = None
    fib_618 = retrace.get("0.618")
    fib_5 = retrace.get("0.5")
    fib_786 = retrace.get("0.786")

    if fib_618 and fib_786:
        golden_lo = min(fib_618, fib_786)
        golden_hi = max(fib_618, fib_786)
        if golden_lo <= close <= golden_hi:
            key_zone = "Golden Pocket (0.618-0.786)"

    if key_zone is None and fib_5:
        if abs(close - fib_5) / close * 100 < 1.5:
            key_zone = "50% Retracement Zone"

    if key_zone is None and fib_618:
        if abs(close - fib_618) / close * 100 < 1.5:
            key_zone = "0.618 Level (Golden Ratio)"

    # Retracement depth
    swing_high = fib_levels["swing_high"]
    swing_low = fib_levels["swing_low"]
    rng = swing_high - swing_low
    if rng > 0:
        if fib_levels["trend"] == "uptrend":
            depth = ((swing_high - close) / rng) * 100
        else:
            depth = ((close - swing_low) / rng) * 100
    else:
        depth = 0
    depth = _safe_round(max(0, depth), 1)

    # Supports and resistances from fib levels
    fib_supports = [{"ratio": r, "price": p} for r, p in sorted_levels if p < close]
    fib_resistances = [{"ratio": r, "price": p} for r, p in sorted_levels if p > close]
    # Nearest supports first, nearest resistances first
    fib_supports = sorted(fib_supports, key=lambda x: x["price"], reverse=True)
    fib_resistances = sorted(fib_resistances, key=lambda x: x["price"])

    return {
        "current_zone": current_zone,
        "retracement_depth_pct": depth,
        "nearest_level": {
            "ratio": nearest[0],
            "price": nearest[1],
            "distance_pct": nearest_dist_pct,
        },
        "key_zone": key_zone,
        "fib_supports": fib_supports,
        "fib_resistances": fib_resistances,
    }
