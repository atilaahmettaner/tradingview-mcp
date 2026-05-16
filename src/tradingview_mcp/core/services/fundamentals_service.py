"""
Fundamentals Service — Yahoo Finance quoteSummary endpoint.

Why this exists: a real investment analyst doesn't decide on a position from
charts alone — they look at the business behind the ticker. This service
pulls valuation multiples, profitability ratios, growth, balance-sheet
health, and dividend info in one call.

Data source: Yahoo Finance quoteSummary API (free, no key). Same proxy
infrastructure as yahoo_finance_service. Returns error dicts on failure
rather than raising, matching the rest of the codebase.

Symbols supported: anything Yahoo recognises — AAPL, MSFT, TSLA, THYAO.IS,
SASA.IS, COMI.CA, etc. Crypto (BTC-USD) has limited fundamental data;
we return what's available without erroring.
"""
from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.proxy_manager import build_opener_with_proxy

_TIMEOUT = 15
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BASE = "https://query2.finance.yahoo.com/v10/finance/quoteSummary"

_MODULES = (
    "summaryDetail,defaultKeyStatistics,financialData,"
    "incomeStatementHistory,balanceSheetHistory,cashflowStatementHistory,"
    "calendarEvents,price"
)

# Yahoo started gating quoteSummary behind a crumb+cookie session in 2024.
# Cache the session for ~25min so we don't re-handshake on every call.
_CRUMB_CACHE: dict = {"crumb": None, "cookies": None, "ts": 0.0}
_CRUMB_TTL_SECONDS = 1500


def _new_session_opener() -> urllib.request.OpenerDirector:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", _UA),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return opener


def _get_crumb_and_opener() -> tuple[str, urllib.request.OpenerDirector]:
    """Establish a Yahoo session: cookies via fc.yahoo.com, then crumb token.

    Cached for 25 minutes. Returns (crumb_string, opener_with_cookies).
    """
    now = time.time()
    if _CRUMB_CACHE["crumb"] and (now - _CRUMB_CACHE["ts"]) < _CRUMB_TTL_SECONDS:
        return _CRUMB_CACHE["crumb"], _CRUMB_CACHE["opener"]

    opener = _new_session_opener()
    # Step 1: hit fc.yahoo.com to drop session cookies
    try:
        opener.open("https://fc.yahoo.com/", timeout=_TIMEOUT)
    except urllib.error.HTTPError:
        pass  # any HTTP status is fine — we just need Set-Cookie
    except urllib.error.URLError:
        pass

    # Step 2: ask for a crumb token
    req = urllib.request.Request(
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
        headers={"User-Agent": _UA, "Accept": "text/plain"},
    )
    with opener.open(req, timeout=_TIMEOUT) as resp:
        crumb = resp.read().decode("utf-8").strip()
    if not crumb or len(crumb) > 100:
        raise ValueError(f"unexpected crumb response: {crumb[:80]!r}")

    _CRUMB_CACHE.update(crumb=crumb, opener=opener, ts=now)
    return crumb, opener


def _fetch(symbol: str) -> dict:
    try:
        crumb, opener = _get_crumb_and_opener()
    except (urllib.error.URLError, ValueError) as e:
        raise ValueError(f"Yahoo crumb handshake failed: {e}")

    url = f"{_BASE}/{symbol}?modules={_MODULES}&crumb={urllib.parse.quote(crumb)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with opener.open(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Crumb may have expired — invalidate cache and retry once
        if e.code in (401, 403):
            _CRUMB_CACHE["crumb"] = None
            crumb, opener = _get_crumb_and_opener()
            url = f"{_BASE}/{symbol}?modules={_MODULES}&crumb={urllib.parse.quote(crumb)}"
            req = urllib.request.Request(
                url, headers={"User-Agent": _UA, "Accept": "application/json"}
            )
            with opener.open(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        else:
            raise

    result = data.get("quoteSummary", {}).get("result")
    if not result:
        err = data.get("quoteSummary", {}).get("error") or "no result"
        raise ValueError(f"Yahoo returned no fundamentals: {err}")
    return result[0]


def _raw(node: dict, key: str) -> Optional[float]:
    """Yahoo wraps numerics as {raw: x, fmt: "..."}; pull the raw."""
    v = node.get(key)
    if isinstance(v, dict):
        return v.get("raw")
    return v


def _pct(value: Optional[float]) -> Optional[float]:
    """Yahoo returns fractions (0.234) for ratios — convert to percent for display."""
    if value is None:
        return None
    return round(value * 100, 2)


def _label_pe(pe: Optional[float]) -> str:
    if pe is None or pe <= 0:
        return "N/A (negative earnings or unavailable)"
    if pe < 15:
        return "Undervalued vs market"
    if pe < 25:
        return "Fair value"
    if pe < 40:
        return "Premium / growth-priced"
    return "Expensive — priced for perfection"


def _label_debt_equity(de: Optional[float]) -> str:
    if de is None:
        return "N/A"
    # Yahoo returns the raw ratio (e.g. 1.5 means 150%). Some tickers report
    # this as a percentage already (150 instead of 1.5). Normalise both ways.
    val = de / 100 if de > 5 else de
    if val < 0.5:
        return "Conservative balance sheet"
    if val < 1.0:
        return "Moderate leverage"
    if val < 2.0:
        return "High leverage"
    return "Heavy debt load — risk of distress"


def _label_roe(roe_pct: Optional[float]) -> str:
    if roe_pct is None:
        return "N/A"
    if roe_pct < 0:
        return "Loss-making — capital being destroyed"
    if roe_pct < 10:
        return "Below average return on equity"
    if roe_pct < 20:
        return "Healthy return on equity"
    return "Exceptional return on equity"


def get_fundamentals(symbol: str) -> dict:
    """Fetch valuation, profitability, growth, balance sheet, and verdict.

    Args:
        symbol: Yahoo Finance ticker — AAPL, MSFT, TSLA, THYAO.IS, etc.

    Returns:
        Structured dict with sections: identity, valuation, profitability,
        growth, balance_sheet, dividend, verdict. Missing fields are None,
        not omitted, so consumers can format consistently.
    """
    symbol = symbol.upper().strip()
    try:
        node = _fetch(symbol)
    except (urllib.error.URLError, json.JSONDecodeError, ValueError) as e:
        return {"symbol": symbol, "error": f"{type(e).__name__}: {e}", "source": "Yahoo Finance"}

    summary = node.get("summaryDetail", {})
    stats = node.get("defaultKeyStatistics", {})
    fin = node.get("financialData", {})
    price = node.get("price", {})

    pe_trailing = _raw(summary, "trailingPE")
    pe_forward = _raw(summary, "forwardPE")
    pb = _raw(stats, "priceToBook")
    ps = _raw(summary, "priceToSalesTrailing12Months")
    market_cap = _raw(price, "marketCap")
    enterprise_value = _raw(stats, "enterpriseValue")
    ev_ebitda = _raw(stats, "enterpriseToEbitda")

    eps_trailing = _raw(stats, "trailingEps")
    eps_forward = _raw(stats, "forwardEps")
    roe = _pct(_raw(fin, "returnOnEquity"))
    roa = _pct(_raw(fin, "returnOnAssets"))
    profit_margin = _pct(_raw(fin, "profitMargins"))
    operating_margin = _pct(_raw(fin, "operatingMargins"))

    revenue_growth = _pct(_raw(fin, "revenueGrowth"))
    earnings_growth = _pct(_raw(fin, "earningsGrowth"))
    total_revenue = _raw(fin, "totalRevenue")
    free_cash_flow = _raw(fin, "freeCashflow")
    operating_cash_flow = _raw(fin, "operatingCashflow")

    debt_to_equity = _raw(fin, "debtToEquity")
    current_ratio = _raw(fin, "currentRatio")
    quick_ratio = _raw(fin, "quickRatio")
    total_cash = _raw(fin, "totalCash")
    total_debt = _raw(fin, "totalDebt")

    dividend_yield = _pct(_raw(summary, "dividendYield"))
    dividend_rate = _raw(summary, "dividendRate")
    payout_ratio = _pct(_raw(summary, "payoutRatio"))
    ex_div = summary.get("exDividendDate", {})
    ex_div_ts = ex_div.get("raw") if isinstance(ex_div, dict) else None
    ex_div_date = (
        datetime.fromtimestamp(ex_div_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if ex_div_ts else None
    )

    target_high = _raw(fin, "targetHighPrice")
    target_low = _raw(fin, "targetLowPrice")
    target_mean = _raw(fin, "targetMeanPrice")
    analyst_recommendation = fin.get("recommendationKey")
    analyst_count = _raw(fin, "numberOfAnalystOpinions")

    # ── Verdict synthesis ─────────────────────────────────────────────
    flags_bullish: list[str] = []
    flags_bearish: list[str] = []

    if pe_trailing and 0 < pe_trailing < 20:
        flags_bullish.append(f"P/E {pe_trailing:.1f} below growth-stock threshold")
    elif pe_trailing and pe_trailing > 40:
        flags_bearish.append(f"P/E {pe_trailing:.1f} priced for high growth")

    if roe and roe > 15:
        flags_bullish.append(f"ROE {roe:.1f}% indicates efficient capital use")
    elif roe is not None and roe < 5:
        flags_bearish.append(f"ROE {roe:.1f}% — weak return on equity")

    if revenue_growth and revenue_growth > 15:
        flags_bullish.append(f"Revenue growing {revenue_growth:.1f}% YoY")
    elif revenue_growth is not None and revenue_growth < 0:
        flags_bearish.append(f"Revenue contracting {revenue_growth:.1f}% YoY")

    if free_cash_flow and free_cash_flow > 0 and market_cap:
        fcf_yield = free_cash_flow / market_cap * 100
        if fcf_yield > 5:
            flags_bullish.append(f"FCF yield {fcf_yield:.1f}% — strong cash generation")

    if debt_to_equity is not None:
        de_norm = debt_to_equity / 100 if debt_to_equity > 5 else debt_to_equity
        if de_norm > 2:
            flags_bearish.append(f"Debt/Equity {de_norm:.2f} — heavy leverage")

    if profit_margin is not None and profit_margin < 0:
        flags_bearish.append(f"Operating at a loss ({profit_margin:.1f}% margin)")

    bull_count = len(flags_bullish)
    bear_count = len(flags_bearish)
    if bull_count >= 3 and bear_count == 0:
        verdict = "STRONG_FUNDAMENTAL_BUY"
    elif bull_count > bear_count + 1:
        verdict = "FUNDAMENTAL_BUY"
    elif bear_count > bull_count + 1:
        verdict = "FUNDAMENTAL_SELL"
    elif bear_count >= 3:
        verdict = "STRONG_FUNDAMENTAL_SELL"
    else:
        verdict = "FUNDAMENTAL_HOLD"

    return {
        "symbol": symbol,
        "name": price.get("longName") or price.get("shortName"),
        "sector": stats.get("category"),
        "currency": price.get("currency"),
        "source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "valuation": {
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "pe_trailing": pe_trailing,
            "pe_forward": pe_forward,
            "price_to_book": pb,
            "price_to_sales": ps,
            "ev_to_ebitda": ev_ebitda,
            "pe_assessment": _label_pe(pe_trailing),
        },
        "profitability": {
            "eps_trailing": eps_trailing,
            "eps_forward": eps_forward,
            "roe_pct": roe,
            "roa_pct": roa,
            "profit_margin_pct": profit_margin,
            "operating_margin_pct": operating_margin,
            "roe_assessment": _label_roe(roe),
        },
        "growth": {
            "revenue_growth_yoy_pct": revenue_growth,
            "earnings_growth_yoy_pct": earnings_growth,
            "total_revenue_ttm": total_revenue,
        },
        "cash_flow": {
            "free_cash_flow": free_cash_flow,
            "operating_cash_flow": operating_cash_flow,
            "fcf_yield_pct": (
                round(free_cash_flow / market_cap * 100, 2)
                if (free_cash_flow and market_cap) else None
            ),
        },
        "balance_sheet": {
            "debt_to_equity": debt_to_equity,
            "current_ratio": current_ratio,
            "quick_ratio": quick_ratio,
            "total_cash": total_cash,
            "total_debt": total_debt,
            "leverage_assessment": _label_debt_equity(debt_to_equity),
        },
        "dividend": {
            "yield_pct": dividend_yield,
            "rate_annual": dividend_rate,
            "payout_ratio_pct": payout_ratio,
            "ex_dividend_date": ex_div_date,
        },
        "analyst_targets": {
            "mean": target_mean,
            "high": target_high,
            "low": target_low,
            "recommendation": analyst_recommendation,
            "analyst_count": analyst_count,
        },
        "verdict": {
            "label": verdict,
            "bullish_factors": flags_bullish,
            "bearish_factors": flags_bearish,
            "bull_score": bull_count,
            "bear_score": bear_count,
        },
    }


def compare_peers(symbols: list[str]) -> dict:
    """Side-by-side fundamental comparison across multiple tickers.

    Returns a rows-of-metrics table plus per-metric leader. Useful for
    "is AAPL cheaper than MSFT and NVDA right now?" questions.
    """
    symbols = [s.upper().strip() for s in symbols if s and s.strip()][:8]
    if not symbols:
        return {"error": "no symbols provided"}

    rows: list[dict] = []
    for s in symbols:
        f = get_fundamentals(s)
        if "error" in f:
            rows.append({"symbol": s, "error": f["error"]})
            continue
        rows.append({
            "symbol": s,
            "name": f.get("name"),
            "market_cap": f["valuation"]["market_cap"],
            "pe_trailing": f["valuation"]["pe_trailing"],
            "pe_forward": f["valuation"]["pe_forward"],
            "price_to_book": f["valuation"]["price_to_book"],
            "ev_to_ebitda": f["valuation"]["ev_to_ebitda"],
            "roe_pct": f["profitability"]["roe_pct"],
            "profit_margin_pct": f["profitability"]["profit_margin_pct"],
            "revenue_growth_pct": f["growth"]["revenue_growth_yoy_pct"],
            "debt_to_equity": f["balance_sheet"]["debt_to_equity"],
            "dividend_yield_pct": f["dividend"]["yield_pct"],
            "fcf_yield_pct": f["cash_flow"]["fcf_yield_pct"],
            "verdict": f["verdict"]["label"],
        })

    def _leader(metric: str, higher_better: bool) -> Optional[str]:
        candidates = [
            (r["symbol"], r[metric]) for r in rows
            if r.get(metric) is not None and not isinstance(r.get(metric), str)
        ]
        if not candidates:
            return None
        if metric == "pe_trailing" or metric == "pe_forward" or metric == "ev_to_ebitda" or metric == "price_to_book":
            candidates = [(s, v) for s, v in candidates if v > 0]
            if not candidates:
                return None
        candidates.sort(key=lambda x: x[1], reverse=higher_better)
        return candidates[0][0]

    leaders = {
        "cheapest_pe":         _leader("pe_trailing",       higher_better=False),
        "highest_growth":      _leader("revenue_growth_pct", higher_better=True),
        "highest_roe":         _leader("roe_pct",            higher_better=True),
        "highest_margin":      _leader("profit_margin_pct",  higher_better=True),
        "lowest_leverage":     _leader("debt_to_equity",     higher_better=False),
        "highest_fcf_yield":   _leader("fcf_yield_pct",      higher_better=True),
        "highest_dividend":    _leader("dividend_yield_pct", higher_better=True),
    }

    return {
        "symbols": symbols,
        "comparison": rows,
        "leaders": leaders,
        "source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_dividend_info(symbol: str) -> dict:
    """Standalone dividend-focused view: yield, payout, sustainability flags.

    For income investors who only care about the dividend story.
    """
    f = get_fundamentals(symbol)
    if "error" in f:
        return f

    div = f["dividend"]
    fcf = f["cash_flow"]["free_cash_flow"]
    payout = div.get("payout_ratio_pct")
    yield_pct = div.get("yield_pct")

    sustainability: list[str] = []
    if payout is not None:
        if payout < 50:
            sustainability.append("Low payout ratio — strong room to grow dividend")
        elif payout < 75:
            sustainability.append("Moderate payout ratio — dividend likely safe")
        elif payout < 100:
            sustainability.append("High payout ratio — limited cushion")
        else:
            sustainability.append("Payout > 100% — dividend funded from outside earnings, risk of cut")

    if fcf is not None and div.get("rate_annual") is not None and fcf > 0:
        sustainability.append(f"FCF positive ({fcf:,.0f}) — supports cash dividend payments")
    elif fcf is not None and fcf < 0:
        sustainability.append("FCF negative — dividend not currently covered by cash flow")

    if yield_pct is None or yield_pct == 0:
        income_grade = "NON_PAYING"
    elif yield_pct < 2:
        income_grade = "LOW_YIELD"
    elif yield_pct < 4:
        income_grade = "STANDARD_YIELD"
    elif yield_pct < 7:
        income_grade = "HIGH_YIELD"
    else:
        income_grade = "ULTRA_HIGH_YIELD_CHECK_FOR_TRAPS"

    return {
        "symbol": f["symbol"],
        "name": f.get("name"),
        "yield_pct": yield_pct,
        "annual_rate": div.get("rate_annual"),
        "payout_ratio_pct": payout,
        "ex_dividend_date": div.get("ex_dividend_date"),
        "income_grade": income_grade,
        "sustainability_notes": sustainability,
        "source": "Yahoo Finance",
    }
