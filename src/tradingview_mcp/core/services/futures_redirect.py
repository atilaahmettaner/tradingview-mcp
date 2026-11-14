"""Answer futures and commodity requests made to the TA tools.

AI clients read "NYMEX CL1!" or "COMEX GC1!" off a futures overview and pass
the futures venue to coin_analysis as ``exchange``, or ask for oil as
TVC:USOIL or OANDA:BCOUSD. The TA tools run on TradingView's stock, crypto,
forex and CFD scanners, which carry none of these, so those calls failed with
INVALID_EXCHANGE, SYMBOL_NOT_FOUND or NO_DATA: 21 calls in the 30 days to
2026-11-14 on the hosted server. The futures tools serve these contracts. A
TA tool routes such a request before it validates the exchange:

- Precious metals (GC1!, SI1!, PL1!, PA1!) keep their analysis. The symbol
  aliases already map them to TVC's spot feeds, which the TA tools serve, so
  only the futures venue is swapped for TVC, and the answer says so.
- Other contracts, and the commodity and index CFDs the scanners don't
  serve, get an answer naming the futures contract and the futures_* call
  that quotes it, instead of an error.
- VIX on Cboe goes to yahoo_price / market_snapshot.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

from tradingview_mcp.core.services.futures_service import FUTURES_WATCHLIST
from tradingview_mcp.core.utils.validators import (
    _TA_ONLY_SCREENERS,
    _TRADINGVIEW_SYMBOL_ALIASES,
)

# Futures venues by the names TradingView and AI clients use for them. None of
# them is an exchange the TA tools accept.
FUTURES_VENUES = frozenset({
    "cme", "cme_mini", "globex", "comex", "comex_mini", "nymex", "nymex_mini",
    "cbot", "cbot_mini", "cboe", "cfe", "ice", "iceus", "iceeur", "iceeu",
    "icesg", "eurex", "nybot",
})

# The forex/CFD venues the TA tools accept (OANDA, TVC, Capital.com …): where
# the CFD names below are asked for.
_CFD_VENUES = frozenset(_TA_ONLY_SCREENERS)

_CATEGORY_OF = {c: cat for cat, contracts in FUTURES_WATCHLIST.items() for c in contracts}
_CONTRACT_BY_TICKER = {c.split(":", 1)[1]: c for c in _CATEGORY_OF}

# Commodity and index CFDs TradingView's scanners don't serve (TVC:USOIL,
# OANDA:BCOUSD, CAPITALCOM:US30 … return no rows), by the futures contract on
# the same underlying.
_CFD_CONTRACT = {
    "USOIL": "NYMEX:CL1!", "WTICOUSD": "NYMEX:CL1!", "OIL_CRUDE": "NYMEX:CL1!",
    "UKOIL": "ICEEUR:BRN1!", "BCOUSD": "ICEEUR:BRN1!", "OIL_BRENT": "ICEEUR:BRN1!",
    "NATGASUSD": "NYMEX:NG1!", "NATURALGAS": "NYMEX:NG1!", "NGAS": "NYMEX:NG1!",
    "XCUUSD": "COMEX:HG1!", "COPPER": "COMEX:HG1!",
    "US30": "CBOT_MINI:YM1!",
    "US500": "CME_MINI:ES1!", "SPX500": "CME_MINI:ES1!",
    "US100": "CME_MINI:NQ1!", "NAS100": "CME_MINI:NQ1!",
    "US2000": "CME_MINI:RTY1!",
    "JP225": "CME:NKD1!",
}
_UNDERLYING = {
    "NYMEX:CL1!": "WTI crude oil", "ICEEUR:BRN1!": "Brent crude oil",
    "NYMEX:NG1!": "natural gas", "COMEX:HG1!": "copper",
    "CBOT_MINI:YM1!": "the Dow Jones", "CME_MINI:ES1!": "the S&P 500",
    "CME_MINI:NQ1!": "the Nasdaq 100", "CME_MINI:RTY1!": "the Russell 2000",
    "CME:NKD1!": "the Nikkei 225",
}
_CATEGORY_LABEL = {
    "equity_index": "equity index", "energy": "energy", "metals": "metals",
    "agriculture": "agriculture", "rates": "interest rate", "forex": "currency",
    "crypto_futures": "crypto",
}

_CONTINUOUS = re.compile(r"^([A-Z0-9]{1,6})([12])!$")  # CL1!, 6E1!, GC2!
_ROOT = re.compile(r"^[A-Z0-9]{1,6}$")                  # CL, ES, 6E
_VIX = ("VIX", "^VIX")


@dataclass(frozen=True)
class FuturesRoute:
    """How a TA tool treats a futures or commodity request.

    Either ``answer`` is set (return it instead of analysing), or
    ``exchange`` is (analyse on that venue instead, and add ``note``)."""
    answer: dict | None = None
    exchange: str | None = None
    note: str | None = None


def route_futures_request(symbol: str, exchange: str, tool: str) -> FuturesRoute | None:
    """Route a TA tool's request when it is for a futures contract, or for a
    commodity or index CFD the scanners don't serve. None for anything else,
    so every other request takes the tool's normal path.

    Args:
        symbol:   The symbol as the caller sent it ("CL1!", "USOIL", "NYMEX:CL1!").
        exchange: The exchange as the caller sent it ("NYMEX", "TVC").
        tool:     The calling tool's name, for the answer's wording.
    """
    sym = (symbol or "").strip().upper()
    ex = (exchange or "").strip().lower()
    if ":" in sym:  # "NYMEX:CL1!" sent as the symbol
        prefix, _, rest = sym.partition(":")
        if prefix.lower() in FUTURES_VENUES or prefix.lower() in _CFD_VENUES:
            ex, sym = prefix.lower(), rest
    on_futures_venue = ex in FUTURES_VENUES
    if on_futures_venue and _ROOT.match(sym) and sym not in _VIX:
        sym += "1!"  # "CL" on NYMEX: its front month
    continuous = _CONTINUOUS.match(sym)
    cfd_contract = _CFD_CONTRACT.get(sym) if ex in _CFD_VENUES else None
    if not (on_futures_venue or continuous or cfd_contract):
        return None
    venue = ex.upper() if ex else "?"

    alias = _TRADINGVIEW_SYMBOL_ALIASES.get(sym, "")
    if alias.startswith("TVC:"):
        if not on_futures_venue:
            return None  # GC1! on an accepted exchange: the alias already works
        metal = alias.split(":", 1)[1].lower()
        return FuturesRoute(
            exchange="tvc",
            note=(
                f"{sym} is {venue} {metal} futures. The TA tools analyse {metal} on "
                f"TradingView's spot feed {alias}, so this is {alias}'s analysis; "
                f"futures_category_snapshot(category=\"metals\") quotes the futures "
                f"contract itself."
            ),
        )

    if sym in _VIX and ex in ("cboe", "cfe"):
        return FuturesRoute(answer=_answer(
            tool, symbol, exchange, asset_class="index", contract=None,
            calls=[
                {"tool": "yahoo_price", "arguments": {"symbol": "^VIX"}},
                {"tool": "market_snapshot", "arguments": {}},
            ],
            note=(
                f"VIX is Cboe's volatility index, and {tool} has no indicators for "
                f"it. yahoo_price(symbol=\"^VIX\") quotes it, and market_snapshot "
                f"includes it with the major indices."
            ),
        ))

    if cfd_contract:
        category = _CATEGORY_OF[cfd_contract]
        underlying = _UNDERLYING[cfd_contract]
        return FuturesRoute(answer=_answer(
            tool, symbol, exchange,
            asset_class="index" if category == "equity_index" else "commodity",
            contract=cfd_contract,
            calls=[{"tool": "futures_category_snapshot", "arguments": {"category": category}}],
            note=(
                f"{sym} on {venue} is a CFD on {underlying}, which TradingView's "
                f"scanners don't serve, so {tool} has no indicators for it. "
                f"{underlying[0].upper()}{underlying[1:]} also trades as the "
                f"{cfd_contract} futures contract: futures_category_snapshot"
                f"(category=\"{category}\") gives its price, change and volume."
            ),
        ))

    front = f"{continuous.group(1)}1!" if continuous else sym
    contract = _CONTRACT_BY_TICKER.get(front)
    if contract:
        category = _CATEGORY_OF[contract]
        later_month = bool(continuous) and continuous.group(2) != "1"
        return FuturesRoute(answer=_answer(
            tool, symbol, exchange, asset_class="futures", contract=contract,
            calls=[{"tool": "futures_category_snapshot", "arguments": {"category": category}}],
            note=(
                f"{sym} is a futures contract. {tool} runs on TradingView's stock, "
                f"crypto, forex and CFD scanners, which have no futures, so it has no "
                f"indicators for it. futures_category_snapshot(category=\"{category}\") "
                f"gives {contract}'s price, change and volume, next to the other "
                f"{_CATEGORY_LABEL[category]} contracts."
                + (f" It quotes the front month, {contract}." if later_month else "")
            ),
        ))

    return FuturesRoute(answer=_answer(
        tool, symbol, exchange, asset_class="futures", contract=None,
        calls=[
            {"tool": "futures_market_overview", "arguments": {"category": "all", "exchanges": "global"}},
            {"tool": "futures_watchlist", "arguments": {}},
        ],
        note=(
            f"{sym} on {venue} looks like a futures contract, and {tool} has no "
            f"futures data. futures_market_overview(exchanges=\"global\") lists the "
            f"most active contracts, and futures_watchlist the {len(_CATEGORY_OF)} "
            f"this server knows by name."
        ),
    ))


def _answer(
    tool: str,
    symbol: str,
    exchange: str,
    *,
    asset_class: str,
    contract: str | None,
    calls: list[dict[str, Any]],
    note: str,
) -> dict[str, Any]:
    """The answer a TA tool returns in place of an error. No "error" key: the
    request was understood, and the call that serves it is named."""
    try:
        print(
            f"[tradingview_mcp] futures redirect: {tool}({symbol!r}, {exchange!r}) "
            f"-> {calls[0]['tool']}",
            file=sys.stderr,
        )
    except Exception:
        pass
    return {
        "symbol": symbol,
        "exchange": exchange,
        "asset_class": asset_class,
        "futures_contract": contract,
        "use_instead": calls,
        "note": note,
    }
