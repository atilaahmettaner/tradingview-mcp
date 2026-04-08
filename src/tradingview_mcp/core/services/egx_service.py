"""
EGX Service — all business logic for Egyptian Exchange (EGX) market tools.

Contains market overview, sector scanning, index analysis, stock screening,
trade plan generation, and Fibonacci retracement analysis.

All public functions return plain dicts / lists and are independently testable
without the MCP layer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from tradingview_mcp.core.services.coinlist import load_symbols
from tradingview_mcp.core.services.indicators import (
    compute_metrics,
    extract_extended_indicators,
    compute_stock_score,
    compute_trade_setup,
    compute_trade_quality,
    compute_fibonacci_levels,
    analyze_fibonacci_position,
    detect_trend_for_fibonacci,
)
from tradingview_mcp.core.utils.validators import EXCHANGE_SCREENER, sanitize_timeframe

try:
    from tradingview_ta import get_multiple_analysis
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False

try:
    from tradingview_screener import Query
    _SCREENER_AVAILABLE = True
except ImportError:
    _SCREENER_AVAILABLE = False


# ── Market Overview ────────────────────────────────────────────────────────────

def get_egx_market_overview(timeframe: str = "1D", limit: int = 10) -> dict:
    """
    Comprehensive EGX market overview: top gainers, losers, most active.

    Args:
        timeframe: TradingView interval (default '1D').
        limit:     Stocks per category (max 20).

    Returns:
        Dict with top_gainers, top_losers, most_active, and market_stats.
    """
    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    symbols = load_symbols("egx")
    if not symbols:
        return {"error": "No EGX symbols found. Check coinlist/egx.txt"}

    screener = EXCHANGE_SCREENER.get("egx", "egypt")
    all_stocks: List[dict] = []
    batch_size = 200

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch)
        except Exception:
            continue

        for sym, data in analysis.items():
            if data is None:
                continue
            try:
                ind = data.indicators
                metrics = compute_metrics(ind)
                if not metrics:
                    continue
                all_stocks.append(
                    {
                        "symbol": sym,
                        "price": metrics.get("price", 0),
                        "changePercent": metrics.get("change", 0),
                        "volume": ind.get("volume", 0),
                        "rsi": round(ind.get("RSI", 0) or 0, 2),
                        "bbw": metrics.get("bbw", 0),
                        "rating": metrics.get("rating", 0),
                        "signal": metrics.get("signal", "N/A"),
                    }
                )
            except Exception:
                continue

    if not all_stocks:
        return {"error": "No data returned for EGX stocks", "timeframe": timeframe}

    by_change = sorted(all_stocks, key=lambda x: x["changePercent"], reverse=True)
    by_volume = sorted(all_stocks, key=lambda x: x["volume"] or 0, reverse=True)

    return {
        "exchange": "EGX",
        "timeframe": timeframe,
        "total_analyzed": len(all_stocks),
        "top_gainers": by_change[:limit],
        "top_losers": by_change[-limit:][::-1],
        "most_active": by_volume[:limit],
        "market_stats": {
            "advancing": len([s for s in all_stocks if s["changePercent"] > 0]),
            "declining": len([s for s in all_stocks if s["changePercent"] < 0]),
            "unchanged": len([s for s in all_stocks if s["changePercent"] == 0]),
            "avg_change": (
                round(sum(s["changePercent"] for s in all_stocks) / len(all_stocks), 2)
                if all_stocks else 0
            ),
        },
    }


# ── Sector Scan ────────────────────────────────────────────────────────────────

def scan_egx_sector(sector: str = "", timeframe: str = "1D", limit: int = 20) -> dict:
    """
    Scan EGX stocks by sector, or list all available sectors.

    Args:
        sector:    Sector key (empty string → list all sectors).
        timeframe: TradingView interval (default '1D').
        limit:     Max results per sector.

    Returns:
        Sector data dict or available sectors list.
    """
    from tradingview_mcp.core.data.egx_sectors import (
        get_all_sectors,
        get_symbols_by_sector,
        get_sector,
    )

    if not sector:
        return {
            "available_sectors": get_all_sectors(),
            "usage": "Pass a sector name to scan. Example: sector='banks'",
        }

    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    sector_key = sector.strip().lower().replace(" ", "_")
    symbols = get_symbols_by_sector(sector_key)

    if not symbols:
        return {
            "error": f"Unknown sector: {sector}",
            "available_sectors": get_all_sectors(),
        }

    screener = EXCHANGE_SCREENER.get("egx", "egypt")

    try:
        analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=symbols)
    except Exception as exc:
        return {"error": f"Analysis failed: {exc}"}

    results: List[dict] = []
    for sym, data in analysis.items():
        if data is None:
            continue
        try:
            ind = data.indicators
            metrics = compute_metrics(ind)
            if not metrics:
                continue
            results.append(
                {
                    "symbol": sym,
                    "sector": get_sector(sym),
                    "price": metrics.get("price", 0),
                    "changePercent": metrics.get("change", 0),
                    "volume": ind.get("volume", 0),
                    "rsi": round(ind.get("RSI", 0) or 0, 2),
                    "bbw": metrics.get("bbw", 0),
                    "rating": metrics.get("rating", 0),
                    "signal": metrics.get("signal", "N/A"),
                    "bb_upper": round(ind.get("BB.upper", 0) or 0, 4),
                    "bb_lower": round(ind.get("BB.lower", 0) or 0, 4),
                    "sma20": round(ind.get("SMA20", 0) or 0, 4),
                    "ema50": round(ind.get("EMA50", 0) or 0, 4),
                }
            )
        except Exception:
            continue

    results.sort(key=lambda x: x["changePercent"], reverse=True)
    sector_changes = [r["changePercent"] for r in results if r["changePercent"] is not None]
    avg_change = round(sum(sector_changes) / len(sector_changes), 2) if sector_changes else 0

    return {
        "exchange": "EGX",
        "sector": sector_key,
        "timeframe": timeframe,
        "total_stocks": len(results),
        "sector_avg_change": avg_change,
        "sector_sentiment": "Bullish" if avg_change > 0.5 else "Bearish" if avg_change < -0.5 else "Neutral",
        "data": results[:limit],
    }


# ── Sector Rotation Scanner ────────────────────────────────────────────────────

def _compute_sector_momentum_score(
    avg_change: float,
    avg_rsi: float,
    breadth_pct: float,
    volume_flow_positive: bool,
    change_rank_pct: float,
) -> int:
    """Compute a 0–100 sector momentum score from four components."""
    change_pts = round(change_rank_pct * 30)

    if 50 <= avg_rsi <= 70:
        rsi_pts = 25
    elif 40 <= avg_rsi < 50 or 70 < avg_rsi <= 80:
        rsi_pts = 15
    elif 30 <= avg_rsi < 40:
        rsi_pts = 10
    elif avg_rsi > 80:
        rsi_pts = 5
    else:
        rsi_pts = 8

    breadth_pts = round(min(breadth_pct, 100) / 100 * 25)
    volume_pts = 20 if volume_flow_positive else 0
    return max(0, min(100, change_pts + rsi_pts + breadth_pts + volume_pts))


def _generate_rotation_signals(ranked_sectors: list) -> List[str]:
    """Generate human-readable money-rotation signals from a ranked heatmap."""
    signals: List[str] = []
    for s in ranked_sectors:
        if s["status"] == "Hot":
            signals.append(
                f"Money rotating INTO {s['display_name']} "
                f"(Hot, {s['avg_change_pct']:+.2f}% avg, "
                f"{s['volume_flow']['signal'].lower()}, "
                f"weight {s['market_cap_weight']}%)"
            )
        elif s["status"] == "Cold":
            signals.append(
                f"Money rotating OUT OF {s['display_name']} "
                f"(Cold, {s['avg_change_pct']:+.2f}% avg, "
                f"{s['volume_flow']['signal'].lower()}, "
                f"weight {s['market_cap_weight']}%)"
            )
    return signals


def run_egx_sector_scanner(
    timeframe: str = "1D",
    top_n_sectors: int = 5,
    top_n_stocks: int = 3,
    min_stock_score: int = 60,
) -> dict:
    """
    Full EGX sector rotation scanner — ranks all 18 sectors and surfaces picks.

    Args:
        timeframe:       TradingView interval (default '1D').
        top_n_sectors:   Number of top sectors to surface stock picks for.
        top_n_stocks:    Number of top stocks per highlighted sector.
        min_stock_score: Minimum stock score for picks (0–100).

    Returns:
        Weighted market view, sector heatmap, top picks, and rotation signals.
    """
    from tradingview_mcp.core.data.egx_sectors import (
        EGX_SECTORS,
        EGX_SECTOR_META,
        SECTOR_DISPLAY_NAMES,
        get_sector,
        get_currency,
    )

    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    screener = EXCHANGE_SCREENER.get("egx", "egypt")

    # Step A: collect all sector symbols
    sector_symbol_map: Dict[str, List[str]] = {}
    all_symbols: List[str] = []
    symbol_to_sectors: Dict[str, List[str]] = {}

    for sector_key, sym_set in EGX_SECTORS.items():
        prefixed = [f"EGX:{s}" for s in sorted(sym_set)]
        sector_symbol_map[sector_key] = prefixed
        for s in prefixed:
            all_symbols.append(s)
            symbol_to_sectors.setdefault(s, []).append(sector_key)

    unique_symbols = list(dict.fromkeys(all_symbols))

    # Step B: batch fetch TA data
    raw_data: Dict[str, Any] = {}
    batch_size = 200
    for i in range(0, len(unique_symbols), batch_size):
        batch = unique_symbols[i : i + batch_size]
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch)
            for sym, data in analysis.items():
                if data is not None:
                    try:
                        ind = data.indicators
                        o = ind.get("open")
                        c = ind.get("close")
                        if o and c and o > 0:
                            raw_data[sym] = {"indicators": ind, "change": ((c - o) / o) * 100}
                    except Exception:
                        continue
        except Exception:
            continue

    if not raw_data:
        return {"error": "No data returned for EGX stocks", "timeframe": timeframe}

    # Step C: cross-sectional percentile ranks
    all_changes = sorted([d["change"] for d in raw_data.values()])
    n_total = len(all_changes)

    def _pct_rank(val: float) -> float:
        count_below = sum(1 for c in all_changes if c < val)
        return count_below / n_total if n_total > 0 else 0.5

    # Step D: per-stock scoring
    stock_scores: Dict[str, Dict[str, Any]] = {}
    for sym, d in raw_data.items():
        try:
            pct_rank = _pct_rank(d["change"])
            ccy = get_currency(sym)
            result = compute_stock_score(d["indicators"], change_pct_rank=pct_rank, currency=ccy)
            if result:
                stock_scores[sym] = {
                    "score_result": result,
                    "change": d["change"],
                    "indicators": d["indicators"],
                }
        except Exception:
            continue

    # Step E: sector aggregation
    sector_agg: Dict[str, Dict[str, Any]] = {}
    for sector_key, symbols in sector_symbol_map.items():
        changes, rsis, scores = [], [], []
        advancing = declining = 0
        net_volume_flow = 0.0
        total_stocks = 0
        sector_stock_data: List[dict] = []

        for sym in symbols:
            if sym not in raw_data:
                continue
            total_stocks += 1
            d = raw_data[sym]
            ind = d["indicators"]
            chg = d["change"]
            changes.append(chg)

            if chg > 0:
                advancing += 1
            elif chg < 0:
                declining += 1

            rsi = ind.get("RSI")
            if rsi is not None:
                rsis.append(rsi)

            vol = ind.get("volume", 0) or 0
            vol_sma = ind.get("volume.SMA20", 0) or 0
            net_volume_flow += vol - vol_sma

            if sym in stock_scores:
                sc = stock_scores[sym]
                scores.append(sc["score_result"]["score"])
                sector_stock_data.append(
                    {
                        "symbol": sym,
                        "score_result": sc["score_result"],
                        "change": sc["change"],
                        "indicators": sc["indicators"],
                    }
                )

        if total_stocks == 0:
            sector_agg[sector_key] = {"status": "No Data", "total_stocks": 0}
            continue

        sector_agg[sector_key] = {
            "avg_change": round(sum(changes) / len(changes), 2) if changes else 0.0,
            "avg_rsi": round(sum(rsis) / len(rsis), 2) if rsis else 50.0,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "advancing": advancing,
            "declining": declining,
            "total_stocks": total_stocks,
            "breadth_pct": round(advancing / total_stocks * 100, 1),
            "net_volume_flow": net_volume_flow,
            "volume_flow_positive": net_volume_flow > 0,
            "stock_data": sector_stock_data,
        }

    # Step F: sector ranking
    valid_sectors = [k for k, v in sector_agg.items() if v.get("total_stocks", 0) > 0]
    sorted_by_change = sorted(valid_sectors, key=lambda k: sector_agg[k]["avg_change"])
    change_rank_map = {
        k: i / len(sorted_by_change) if len(sorted_by_change) > 1 else 0.5
        for i, k in enumerate(sorted_by_change)
    }

    for sector_key in valid_sectors:
        agg = sector_agg[sector_key]
        momentum = _compute_sector_momentum_score(
            avg_change=agg["avg_change"],
            avg_rsi=agg["avg_rsi"],
            breadth_pct=agg["breadth_pct"],
            volume_flow_positive=agg["volume_flow_positive"],
            change_rank_pct=change_rank_map.get(sector_key, 0.5),
        )
        agg["momentum_score"] = momentum
        if momentum >= 65 and agg["volume_flow_positive"]:
            agg["status"] = "Hot"
        elif momentum >= 50 or (agg["avg_change"] > 0 and agg["breadth_pct"] > 50):
            agg["status"] = "Warming"
        elif momentum >= 35 and not agg["volume_flow_positive"]:
            agg["status"] = "Cooling"
        else:
            agg["status"] = "Cold"

    # Build heatmap
    heatmap: List[dict] = []
    for sector_key in sorted(
        valid_sectors,
        key=lambda k: sector_agg[k].get("momentum_score", 0),
        reverse=True,
    ):
        agg = sector_agg[sector_key]
        meta = EGX_SECTOR_META.get(sector_key, {})
        heatmap.append(
            {
                "sector": sector_key,
                "display_name": SECTOR_DISPLAY_NAMES.get(sector_key, sector_key),
                "market_cap_weight": meta.get("market_cap_weight", 0),
                "status": agg["status"],
                "momentum_score": agg.get("momentum_score", 0),
                "avg_change_pct": agg["avg_change"],
                "avg_rsi": agg["avg_rsi"],
                "avg_stock_score": agg["avg_score"],
                "breadth": {
                    "advancing": agg["advancing"],
                    "declining": agg["declining"],
                    "breadth_pct": agg["breadth_pct"],
                },
                "volume_flow": {
                    "net_flow": round(agg["net_volume_flow"]),
                    "signal": "Inflow" if agg["volume_flow_positive"] else "Outflow",
                },
                "stocks_analyzed": agg["total_stocks"],
            }
        )

    for sector_key in EGX_SECTORS:
        if sector_key not in valid_sectors:
            meta = EGX_SECTOR_META.get(sector_key, {})
            heatmap.append(
                {
                    "sector": sector_key,
                    "display_name": SECTOR_DISPLAY_NAMES.get(sector_key, sector_key),
                    "market_cap_weight": meta.get("market_cap_weight", 0),
                    "status": "No Data",
                    "momentum_score": 0,
                    "avg_change_pct": 0,
                    "avg_rsi": 0,
                    "avg_stock_score": 0,
                    "breadth": {"advancing": 0, "declining": 0, "breadth_pct": 0},
                    "volume_flow": {"net_flow": 0, "signal": "N/A"},
                    "stocks_analyzed": 0,
                }
            )

    # Step G: weighted market view
    weighted_change = weighted_rsi = weighted_momentum = total_weight = 0.0
    for sector_key in valid_sectors:
        agg = sector_agg[sector_key]
        weight = EGX_SECTOR_META.get(sector_key, {}).get("market_cap_weight", 0)
        weighted_change += agg["avg_change"] * weight
        weighted_rsi += agg["avg_rsi"] * weight
        weighted_momentum += agg.get("momentum_score", 0) * weight
        total_weight += weight

    if total_weight > 0:
        weighted_change = round(weighted_change / total_weight, 2)
        weighted_rsi = round(weighted_rsi / total_weight, 2)
        weighted_momentum = round(weighted_momentum / total_weight, 1)
    else:
        weighted_change = weighted_rsi = weighted_momentum = 0  # type: ignore[assignment]

    market_sentiment = (
        "Bullish" if weighted_change > 0.5
        else "Bearish" if weighted_change < -0.5
        else "Neutral"
    )

    # Step H: top picks
    top_sector_keys = [h["sector"] for h in heatmap[:top_n_sectors] if h["status"] != "No Data"]
    sector_top_picks: Dict[str, list] = {}

    for sector_key in top_sector_keys:
        agg = sector_agg[sector_key]
        candidates = agg.get("stock_data", [])
        qualified = [c for c in candidates if c["score_result"]["score"] >= min_stock_score]
        qualified.sort(key=lambda x: x["score_result"]["score"], reverse=True)

        picks: List[dict] = []
        for c in qualified[:top_n_stocks]:
            result = c["score_result"]
            ind = c["indicators"]
            metrics = compute_metrics(ind)
            currency = get_currency(c["symbol"])
            entry: dict = {
                "symbol": c["symbol"],
                "price": metrics["price"] if metrics else 0,
                "currency": currency,
                "stock_score": result["score"],
                "grade": result["grade"],
                "trend_state": result["trend_state"],
                "change_pct": result["change_pct"],
                "signals": result["signals"],
                "penalties": result.get("penalties", []),
                "liquidity": result.get("liquidity", {}),
            }
            if result["score"] >= 70:
                setup = compute_trade_setup(ind)
                if setup:
                    quality = compute_trade_quality(ind, result["score"], setup)
                    entry["trade_setup"] = {
                        "setup_types": setup["setup_types"],
                        "entry_points": setup["entry_points"],
                        "stop_loss": setup["stop_loss"],
                        "stop_distance_pct": setup["stop_distance_pct"],
                        "targets": setup["targets"],
                        "risk_reward": setup["risk_reward"],
                        "supports": setup["supports"],
                        "resistances": setup["resistances"],
                    }
                    entry["trade_quality_score"] = quality["trade_quality_score"]
                    entry["trade_quality"] = quality["quality"]
            picks.append(entry)
        sector_top_picks[sector_key] = picks

    return {
        "exchange": "EGX",
        "timeframe": timeframe,
        "total_sectors": len(heatmap),
        "total_stocks_scanned": len(raw_data),
        "weighted_market_view": {
            "weighted_change_pct": weighted_change,
            "weighted_rsi": weighted_rsi,
            "weighted_momentum": weighted_momentum,
            "market_sentiment": market_sentiment,
        },
        "sector_heatmap": heatmap,
        "sector_top_picks": sector_top_picks,
        "rotation_signals": _generate_rotation_signals(heatmap),
        "disclaimer": "For educational/informational purposes only. Not financial advice.",
    }


# ── Index Analysis ─────────────────────────────────────────────────────────────

def analyze_egx_index(index: str = "EGX30", timeframe: str = "1D", limit: int = 30) -> dict:
    """
    Analyze an EGX index showing constituent performance with full indicators.

    Args:
        index:     Index name (EGX30, EGX70, EGX100, SHARIAH33, EGX35LV, TAMAYUZ).
        timeframe: TradingView interval (default '1D').
        limit:     Maximum number of stocks to show in detail.

    Returns:
        Index statistics, sector breakdown, top gainers/losers, and all_stocks list.
    """
    from tradingview_mcp.core.data.egx_indices import EGX_INDICES, is_egx30_stock
    from tradingview_mcp.core.data.egx_sectors import get_sector

    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    index_key = index.strip().upper()
    if index_key not in EGX_INDICES:
        return {
            "error": f"Unknown index: {index}",
            "available_indices": list(EGX_INDICES.keys()),
            "usage": "Use EGX30, EGX70, or EGX100",
        }

    index_info = EGX_INDICES[index_key]
    symbols = index_info["get_symbols"]()
    screener = EXCHANGE_SCREENER.get("egx", "egypt")

    all_stocks: List[dict] = []
    batch_size = 200
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch)
        except Exception:
            continue

        for sym, data in analysis.items():
            if data is None:
                continue
            try:
                ind = data.indicators
                metrics = compute_metrics(ind)
                if not metrics:
                    continue
                extended = extract_extended_indicators(ind)
                all_stocks.append(
                    {
                        "symbol": sym,
                        "sector": get_sector(sym),
                        "is_egx30": is_egx30_stock(sym),
                        "price": metrics.get("price", 0),
                        "changePercent": metrics.get("change", 0),
                        "volume": ind.get("volume", 0),
                        "rsi": extended["rsi"]["value"],
                        "rsi_signal": extended["rsi"]["signal"],
                        "sma20": extended["sma"]["sma20"],
                        "sma50": extended["sma"]["sma50"],
                        "sma200": extended["sma"]["sma200"],
                        "atr": extended["atr"]["value"],
                        "atr_volatility": extended["atr"]["volatility"],
                        "macd_crossover": extended["macd"]["crossover"],
                        "volume_signal": extended["volume"]["signal"],
                        "bbw": metrics.get("bbw", 0),
                        "bb_rating": metrics.get("rating", 0),
                        "bb_signal": metrics.get("signal", "N/A"),
                    }
                )
            except Exception:
                continue

    if not all_stocks:
        return {"error": f"No data returned for {index_key} constituents", "timeframe": timeframe}

    changes = [s["changePercent"] for s in all_stocks]
    avg_change = sum(changes) / len(changes)
    advancing = len([c for c in changes if c > 0])
    declining = len([c for c in changes if c < 0])
    unchanged = len([c for c in changes if c == 0])

    sector_perf: Dict[str, Any] = {}
    for s in all_stocks:
        sec = s["sector"]
        if sec not in sector_perf:
            sector_perf[sec] = {"stocks": 0, "total_change": 0.0}
        sector_perf[sec]["stocks"] += 1
        sector_perf[sec]["total_change"] += s["changePercent"]

    sector_summary = [
        {
            "sector": sec,
            "stocks_count": data["stocks"],
            "avg_change": round(data["total_change"] / data["stocks"], 2),
        }
        for sec, data in sorted(
            sector_perf.items(),
            key=lambda x: x[1]["total_change"] / x[1]["stocks"],
            reverse=True,
        )
    ]

    by_change = sorted(all_stocks, key=lambda x: x["changePercent"], reverse=True)

    return {
        "index": index_key,
        "index_name": index_info["name"],
        "description": index_info["description"],
        "timeframe": timeframe,
        "index_stats": {
            "total_constituents": index_info["constituents_count"],
            "analyzed": len(all_stocks),
            "avg_change": round(avg_change, 2),
            "advancing": advancing,
            "declining": declining,
            "unchanged": unchanged,
            "breadth": round(advancing / len(all_stocks) * 100, 1) if all_stocks else 0,
            "sentiment": "Bullish" if avg_change > 0.5 else "Bearish" if avg_change < -0.5 else "Neutral",
        },
        "sector_breakdown": sector_summary,
        "top_gainers": by_change[:5],
        "top_losers": by_change[-5:][::-1],
        "all_stocks": by_change[:limit],
    }


# ── Stock Screener ─────────────────────────────────────────────────────────────

def screen_egx_stocks(
    timeframe: str = "1D",
    min_score: int = 55,
    index_filter: str = "",
    limit: int = 20,
) -> dict:
    """
    Production stock ranking engine for EGX — finds strong stocks with setups.

    Args:
        timeframe:    TradingView interval (default '1D').
        min_score:    Minimum stock score to include (0–100).
        index_filter: Filter by index name (empty = all EGX).
        limit:        Maximum results.

    Returns:
        Qualified trades, watchlist, grade distribution, and execution rules.
    """
    from tradingview_mcp.core.data.egx_sectors import get_sector, get_currency

    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    if index_filter:
        from tradingview_mcp.core.data.egx_indices import EGX_INDICES
        idx_key = index_filter.strip().upper()
        if idx_key in EGX_INDICES:
            symbols = EGX_INDICES[idx_key]["get_symbols"]()
            source_label = idx_key
        else:
            return {"error": f"Unknown index: {index_filter}", "available": list(EGX_INDICES.keys())}
    else:
        symbols = load_symbols("egx")
        source_label = "All EGX"

    if not symbols:
        return {"error": "No EGX symbols found."}

    screener = EXCHANGE_SCREENER.get("egx", "egypt")
    raw_results: List[tuple] = []
    batch_size = 200

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch)
        except Exception:
            continue

        for sym, data in analysis.items():
            if data is None:
                continue
            try:
                ind = data.indicators
                o = ind.get("open")
                c = ind.get("close")
                if not o or not c or o <= 0:
                    continue
                raw_results.append((sym, ind, ((c - o) / o) * 100))
            except Exception:
                continue

    if not raw_results:
        return {"error": "No data returned for EGX stocks", "timeframe": timeframe}

    changes = sorted([r[2] for r in raw_results])
    n = len(changes)

    def _pct_rank(val: float) -> float:
        return sum(1 for c in changes if c < val) / n if n > 0 else 0.5

    scored_stocks: List[dict] = []
    for sym, ind, change in raw_results:
        try:
            pct_rank = _pct_rank(change)
            ccy = get_currency(sym)
            result = compute_stock_score(ind, change_pct_rank=pct_rank, currency=ccy)
            if not result or result["score"] < min_score:
                continue
            metrics = compute_metrics(ind)
            if not metrics:
                continue

            vol_sma = ind.get("volume.SMA20")
            liquidity_status = "Pass"
            if vol_sma and vol_sma < 10000:
                liquidity_status = "Fail — Very Low"
                if min_score >= 55:
                    continue

            stock_entry: dict = {
                "symbol": sym,
                "sector": get_sector(sym),
                "price": metrics["price"],
                "stock_score": result["score"],
                "grade": result["grade"],
                "trend_state": result["trend_state"],
                "change_pct": result["change_pct"],
                "score_breakdown": result["breakdown"],
                "signals": result["signals"],
                "penalties": result["penalties"],
                "liquidity_status": liquidity_status,
            }

            if result["score"] >= 70:
                setup = compute_trade_setup(ind)
                if setup:
                    quality = compute_trade_quality(ind, result["score"], setup)
                    stock_entry["trade_setup"] = {
                        "setup_types": setup["setup_types"],
                        "entry_points": setup["entry_points"],
                        "stop_loss": setup["stop_loss"],
                        "stop_distance_pct": setup["stop_distance_pct"],
                        "targets": setup["targets"],
                        "risk_reward": setup["risk_reward"],
                        "supports": setup["supports"],
                        "resistances": setup["resistances"],
                    }
                    stock_entry["trade_quality_score"] = quality["trade_quality_score"]
                    stock_entry["trade_quality"] = quality["quality"]
                    stock_entry["trade_notes"] = quality["notes"]
                    stock_entry["trade_quality_breakdown"] = quality["breakdown"]

            scored_stocks.append(stock_entry)
        except Exception:
            continue

    scored_stocks.sort(
        key=lambda x: (x["stock_score"], x.get("trade_quality_score", 0)),
        reverse=True,
    )

    grades: Dict[str, int] = {}
    for s in scored_stocks:
        g = s["grade"]
        grades[g] = grades.get(g, 0) + 1

    qualified = [s for s in scored_stocks if s["stock_score"] >= 70 and s.get("trade_quality_score", 0) >= 65]
    watchlist = [s for s in scored_stocks if s["stock_score"] < 70 or s.get("trade_quality_score", 0) < 65]

    return {
        "source": source_label,
        "timeframe": timeframe,
        "min_score": min_score,
        "total_scanned": len(raw_results),
        "total_passed": len(scored_stocks),
        "grade_distribution": grades,
        "qualified_trades": qualified[:limit],
        "qualified_count": len(qualified),
        "watchlist": watchlist[: max(5, limit - len(qualified))],
        "execution_rules": {
            "trade_threshold": "Stock Score >= 70 AND Trade Quality >= 65",
            "risk_reward_min": "R:R to Target 2 >= 2.0 preferred",
            "disclaimer": "For educational/informational purposes only. Not financial advice.",
        },
    }


# ── Trade Plan ─────────────────────────────────────────────────────────────────

def generate_egx_trade_plan(symbol: str, timeframe: str = "1D") -> dict:
    """
    Generate a full trade plan for a specific EGX stock.

    Args:
        symbol:    EGX stock symbol (e.g. 'COMI'). Will be prefixed with EGX:.
        timeframe: TradingView interval (default '1D').

    Returns:
        Complete plan: stock score, setup, stop-loss, targets, quality, and S/R.
    """
    from tradingview_mcp.core.data.egx_sectors import get_sector, get_currency

    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    full_symbol = symbol.upper() if ":" in symbol else f"EGX:{symbol.upper()}"
    screener = EXCHANGE_SCREENER.get("egx", "egypt")

    try:
        analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=[full_symbol])
    except Exception as exc:
        return {"error": f"Analysis failed: {exc}"}

    if full_symbol not in analysis or analysis[full_symbol] is None:
        return {"error": f"No data found for {full_symbol}"}

    ind = analysis[full_symbol].indicators
    metrics = compute_metrics(ind)
    if not metrics:
        return {"error": f"Could not compute metrics for {full_symbol}"}

    ccy = get_currency(full_symbol)
    score_result = compute_stock_score(ind, currency=ccy)
    if not score_result:
        return {"error": f"Could not compute stock score for {full_symbol}"}

    setup = compute_trade_setup(ind)
    quality = compute_trade_quality(ind, score_result["score"], setup) if setup else None
    extended = extract_extended_indicators(ind)

    output: dict = {
        "symbol": full_symbol,
        "sector": get_sector(full_symbol),
        "currency": ccy,
        "timeframe": timeframe,
        "price": metrics["price"],
        "change_pct": score_result["change_pct"],
        "stock_score": score_result["score"],
        "grade": score_result["grade"],
        "trend_state": score_result["trend_state"],
        "score_breakdown": score_result["breakdown"],
        "signals": score_result["signals"],
        "penalties": score_result["penalties"],
        "liquidity": score_result.get("liquidity", {}),
        "rsi": extended["rsi"],
        "macd": extended["macd"],
        "adx": extended["adx"],
        "volume": extended["volume"],
        "ema": extended["ema"],
        "bollinger_bands": extended["bollinger_bands"],
        "tv_recommendation": extended["tv_recommendation"],
    }

    if setup:
        output["trade_setup"] = {
            "setup_types": setup["setup_types"],
            "entry_points": setup["entry_points"],
            "stop_loss": setup["stop_loss"],
            "stop_distance_pct": setup["stop_distance_pct"],
            "targets": setup["targets"],
            "risk_reward": setup["risk_reward"],
            "supports": setup["supports"],
            "resistances": setup["resistances"],
        }

    if quality:
        output["trade_quality_score"] = quality["trade_quality_score"]
        output["trade_quality"] = quality["quality"]
        output["trade_quality_breakdown"] = quality["breakdown"]
        output["trade_notes"] = quality["notes"]

    ss = score_result["score"]
    tq = quality["trade_quality_score"] if quality else 0
    rr2 = setup["risk_reward"]["to_target_2"] if setup else 0

    if ss >= 70 and tq >= 65 and rr2 and rr2 >= 2.0:
        recommendation = "QUALIFIED — Strong stock with actionable setup"
    elif ss >= 70 and tq >= 50:
        recommendation = "CONDITIONAL — Good stock but setup needs improvement"
    elif ss >= 55:
        recommendation = "WATCHLIST — Monitor for better entry"
    else:
        recommendation = "AVOID — Does not meet momentum/quality criteria"

    output["recommendation"] = recommendation
    output["disclaimer"] = "For educational/informational purposes only. Not financial advice."
    return output


# ── Fibonacci Retracement ──────────────────────────────────────────────────────

def analyze_egx_fibonacci(
    symbol: str,
    lookback: str = "52W",
    timeframe: str = "1D",
) -> dict:
    """
    Fibonacci retracement analysis for an EGX stock.

    Args:
        symbol:    EGX stock symbol (e.g. 'COMI').
        lookback:  Period for swing high/low — '1M', '3M', '6M', '52W', 'ALL'.
        timeframe: TradingView interval (default '1D').

    Returns:
        Fibonacci retracement & extension levels, price position, and context.
    """
    from tradingview_mcp.core.data.egx_sectors import get_sector, get_currency

    if not _TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    valid_lookbacks = {"1M", "3M", "6M", "52W", "ALL"}
    if lookback not in valid_lookbacks:
        return {"error": f"Invalid lookback: {lookback}", "valid": sorted(valid_lookbacks)}

    full_symbol = symbol.upper() if ":" in symbol else f"EGX:{symbol.upper()}"
    screener = EXCHANGE_SCREENER.get("egx", "egypt")

    LOOKBACK_COLUMNS = {
        "1M": ("High.1M", "Low.1M"),
        "3M": ("High.3M", "Low.3M"),
        "6M": ("High.6M", "Low.6M"),
        "52W": ("price_52_week_high", "price_52_week_low"),
        "ALL": ("High.All", "Low.All"),
    }

    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    swing_source: Optional[str] = None

    if _SCREENER_AVAILABLE:
        try:
            high_col, low_col = LOOKBACK_COLUMNS[lookback]
            q = (
                Query()
                .set_markets("egypt")
                .select("close", high_col, low_col)
                .set_tickers([full_symbol])
            )
            _, df = q.get_scanner_data()
            if not df.empty:
                row = df.iloc[0]
                h = row.get(high_col)
                ll = row.get(low_col)
                if h is not None and ll is not None and h > ll:
                    swing_high = float(h)
                    swing_low = float(ll)
                    swing_source = f"screener ({lookback} period high/low)"
        except Exception:
            pass

    try:
        analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=[full_symbol])
    except Exception as exc:
        return {"error": f"Analysis failed: {exc}"}

    if full_symbol not in analysis or analysis[full_symbol] is None:
        return {"error": f"No data found for {full_symbol}"}

    ind = analysis[full_symbol].indicators
    close = ind.get("close")
    if not close:
        return {"error": f"No price data for {full_symbol}"}

    if swing_high is None or swing_low is None:
        fib_r3 = ind.get("Pivot.M.Fibonacci.R3")
        fib_s3 = ind.get("Pivot.M.Fibonacci.S3")
        classic_r3 = ind.get("Pivot.M.Classic.R3")
        classic_s3 = ind.get("Pivot.M.Classic.S3")
        h_candidate = fib_r3 or classic_r3
        l_candidate = fib_s3 or classic_s3
        if h_candidate and l_candidate and h_candidate > l_candidate:
            swing_high = float(h_candidate)
            swing_low = float(l_candidate)
            swing_source = "pivot points (R3/S3 fallback)"
        else:
            return {
                "error": "Could not determine swing high/low for Fibonacci calculation",
                "hint": "Period high/low data not available for this symbol",
            }

    swing_range_pct = ((swing_high - swing_low) / swing_low) * 100
    if swing_range_pct < 2:
        return {
            "error": f"Swing range too narrow ({swing_range_pct:.1f}%) for meaningful Fibonacci levels",
            "swing_high": round(swing_high, 2),
            "swing_low": round(swing_low, 2),
        }

    ema50 = ind.get("EMA50")
    ema200 = ind.get("EMA200")
    trend, trend_reasoning = detect_trend_for_fibonacci(close, swing_high, swing_low, ema50, ema200)
    fib_levels = compute_fibonacci_levels(swing_high, swing_low, trend)
    position = analyze_fibonacci_position(close, fib_levels)

    rsi_val = ind.get("RSI")
    atr_val = ind.get("ATR")
    vol = ind.get("volume")
    vol_sma = ind.get("volume.SMA20")
    vol_ratio = round(vol / vol_sma, 2) if vol and vol_sma and vol_sma > 0 else None
    change_pct = (
        round(((close - ind.get("open", close)) / ind.get("open", close)) * 100, 2)
        if ind.get("open")
        else None
    )

    interp_parts = [
        f"Price is at {position['retracement_depth_pct']}% retracement of the {trend}."
    ]
    if position.get("key_zone"):
        interp_parts.append(f"Currently in {position['key_zone']}.")
    if position.get("fib_supports"):
        nearest_s = position["fib_supports"][0]
        interp_parts.append(f"Key Fib support at {nearest_s['price']} ({nearest_s['ratio']}).")
    if position.get("fib_resistances"):
        nearest_r = position["fib_resistances"][0]
        interp_parts.append(f"Key Fib resistance at {nearest_r['price']} ({nearest_r['ratio']}).")

    return {
        "symbol": full_symbol,
        "sector": get_sector(full_symbol),
        "timeframe": timeframe,
        "lookback_period": lookback,
        "price": round(close, 2),
        "change_pct": change_pct,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "swing_range_pct": round(swing_range_pct, 1),
        "swing_source": swing_source,
        "trend": trend,
        "trend_reasoning": trend_reasoning,
        "retracement_levels": fib_levels["retracement_levels"],
        "extension_levels": fib_levels["extension_levels"],
        "price_position": position,
        "context": {
            "rsi": round(rsi_val, 1) if rsi_val else None,
            "ema50": round(ema50, 2) if ema50 else None,
            "ema200": round(ema200, 2) if ema200 else None,
            "atr": round(atr_val, 2) if atr_val else None,
            "volume_ratio": vol_ratio,
        },
        "interpretation": " ".join(interp_parts),
        "disclaimer": "For educational/informational purposes only. Not financial advice.",
    }
