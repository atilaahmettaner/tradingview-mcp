"""
AAOIFI Shariah compliance screening service.

The service performs a two-stage screen:
1. Business activity exclusion for prohibited sectors and industries.
2. Financial ratio checks against AAOIFI Standard No. 21 thresholds.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from tradingview_mcp.core.services.options_service import _fetch as _fetch_yahoo_json

logger = logging.getLogger(__name__)

_QUOTE_SUMMARY_BASE = "https://query2.finance.yahoo.com/v10/finance/quoteSummary"
_TIMESERIES_BASE = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries"
_TIMESERIES_TYPES = (
    "annualTotalDebt",
    "annualCashCashEquivalentsAndShortTermInvestments",
    "annualAccountsReceivable",
    "annualNetReceivables",
    "annualTotalRevenue",
    "annualInterestIncome",
    "annualInterestIncomeNonOperating",
)
_PERIOD_START = 493590046

DEBT_THRESHOLD = 0.30
CASH_THRESHOLD = 0.30
RECEIVABLES_THRESHOLD = 0.30
MAX_BULK_SYMBOLS = 20

PROHIBITED_KEYWORDS: tuple[str, ...] = (
    "bank",
    "banking",
    "insurance",
    "conventional finance",
    "credit",
    "mortgage",
    "lending",
    "alcohol",
    "alcoholic",
    "brewery",
    "brewing",
    "winery",
    "distillery",
    "spirits",
    "tobacco",
    "cigarette",
    "cigar",
    "pork",
    "swine",
    "pig farming",
    "gambling",
    "casino",
    "lottery",
    "betting",
    "gaming",
    "adult entertainment",
    "pornography",
    "xxx",
    "weapons",
    "defence",
    "defense contractor",
    "arms",
    "cannabis",
)

PROHIBITED_DESCRIPTION_KEYWORDS: tuple[str, ...] = (
    "conventional banking",
    "conventional finance",
    "insurance company",
    "mortgage lender",
    "payday lending",
    "alcoholic beverages",
    "brewery",
    "breweries",
    "winery",
    "distillery",
    "tobacco products",
    "cigarette",
    "cigar",
    "pork products",
    "pig farming",
    "casino",
    "gambling",
    "lottery",
    "sports betting",
    "adult entertainment",
    "pornography",
    "defense contractor",
    "weapons manufacturer",
    "arms dealer",
    "cannabis",
)

PROHIBITED_INDUSTRIES: tuple[str, ...] = (
    "banks-regional",
    "banks-diversified",
    "insurance-life",
    "insurance-property & casualty",
    "insurance-diversified",
    "insurance-reinsurance",
    "insurance-specialty",
    "asset management",
    "capital markets",
    "financial data & stock exchanges",
    "mortgage finance",
    "credit services",
    "beverages-wineries & distilleries",
    "beverages-brewers",
    "tobacco",
    "gambling",
    "adult entertainment",
    "defense contractors",
    "aerospace & defense",
)


@dataclass
class ShariahResult:
    """Structured result for one AAOIFI Shariah screening report."""

    symbol: str
    name: str
    sector: str
    industry: str
    sector_screen_passed: bool = True
    sector_screen_reason: str = ""
    market_cap: float = 0.0
    total_debt: float = 0.0
    cash_and_securities: float = 0.0
    accounts_receivable: float = 0.0
    total_revenue: float = 0.0
    interest_income: float = 0.0
    interest_income_available: bool = False
    debt_ratio: float = 0.0
    cash_ratio: float = 0.0
    receivables_ratio: float = 0.0
    purification_rate: float = 0.0
    quantitative_passed: bool = True
    failed_ratios: list[str] = field(default_factory=list)
    compliant: bool = False
    verdict: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return an MCP-friendly dictionary report."""

        def pct(value: float) -> str:
            return f"{value * 100:.2f}%"

        def ratio_status(value: float, threshold: float) -> dict:
            return {
                "value": pct(value),
                "passed": value < threshold,
                "limit": pct(threshold),
            }

        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "industry": self.industry,
            "methodology": "AAOIFI Standard No. 21",
            "status": "halal" if self.compliant else "haram",
            "verdict": self.verdict,
            "compliant": self.compliant,
            "screening": {
                "qualitative_screen": {
                    "status": "PASSED" if self.sector_screen_passed else "FAILED",
                    "detail": self.sector_screen_reason
                    or "No prohibited business activity detected",
                },
                "quantitative_screen": {
                    "status": "PASSED" if self.quantitative_passed else "FAILED",
                    "ratios": {
                        "debt_to_market_cap": ratio_status(
                            self.debt_ratio,
                            DEBT_THRESHOLD,
                        ),
                        "cash_securities_to_market_cap": ratio_status(
                            self.cash_ratio,
                            CASH_THRESHOLD,
                        ),
                        "receivables_to_market_cap": ratio_status(
                            self.receivables_ratio,
                            RECEIVABLES_THRESHOLD,
                        ),
                    },
                    "failed_ratios": self.failed_ratios,
                },
            },
            "purification": {
                "rate": pct(self.purification_rate),
                "available": self.interest_income_available,
                "note": (
                    "Donate this percentage of income or dividends received to charity."
                    if self.purification_rate > 0
                    else "No purification required based on available interest income data."
                    if self.interest_income_available
                    else "Unable to calculate purification because interest income data is unavailable."
                ),
            },
            "raw_financials": {
                "market_cap": self.market_cap,
                "total_debt": self.total_debt,
                "cash_and_securities": self.cash_and_securities,
                "accounts_receivable": self.accounts_receivable,
                "total_revenue": self.total_revenue,
                "interest_income": self.interest_income,
            },
            "warnings": self.warnings,
            "disclaimer": (
                "For informational purposes only. Not a fatwa. "
                "Consult a qualified Shariah scholar before investing."
            ),
        }


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert financial statement values to finite floats."""
    try:
        if value is None:
            return default
        parsed = float(value)
        return parsed if parsed == parsed else default
    except (TypeError, ValueError):
        return default


def _normalize_text(value: str) -> str:
    """Normalize punctuation that varies between Yahoo Finance data sources."""
    return (
        value.lower()
        .replace("—", "-")
        .replace("–", "-")
        .replace(" - ", "-")
        .strip()
    )


def _raw_value(value: Any, default: float = 0.0) -> float:
    """Extract Yahoo's common {raw, fmt} value shape as a float."""
    if isinstance(value, dict):
        value = value.get("raw")
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fetch_quote_summary(symbol: str) -> dict:
    """Fetch Yahoo quote summary profile, price, and high-level financial data."""
    modules = "assetProfile,price,financialData"
    encoded_symbol = urllib.parse.quote(symbol)
    url = f"{_QUOTE_SUMMARY_BASE}/{encoded_symbol}?modules={modules}"
    data = _fetch_yahoo_json(url)
    results = data.get("quoteSummary", {}).get("result") or []
    if not results:
        error = data.get("quoteSummary", {}).get("error") or "empty Yahoo quote summary"
        raise ValueError(str(error))
    return results[0]


def _fetch_timeseries(symbol: str) -> dict:
    """Fetch annual Yahoo fundamentals timeseries used by the ratio screen."""
    encoded_symbol = urllib.parse.quote(symbol)
    query = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "type": ",".join(_TIMESERIES_TYPES),
            "period1": _PERIOD_START,
            "period2": int(time.time()),
        }
    )
    url = f"{_TIMESERIES_BASE}/{encoded_symbol}?{query}"
    data = _fetch_yahoo_json(url)
    return data.get("timeseries", {})


def _latest_timeseries_value(timeseries: dict, *type_names: str) -> tuple[float, bool, str]:
    """Return the latest usable raw value for the first matching Yahoo type."""
    results = timeseries.get("result") or []
    wanted = set(type_names)

    for item in results:
        types = item.get("meta", {}).get("type") or []
        matched_types = [type_name for type_name in types if type_name in wanted]
        for type_name in matched_types:
            values = item.get(type_name) or []
            for entry in reversed(values):
                raw = _raw_value(entry.get("reportedValue"))
                if raw == raw:
                    return raw, True, entry.get("asOfDate") or ""
    return 0.0, False, ""


def _matching_period_value(
    timeseries: dict,
    expected_date: str,
    *type_names: str,
) -> tuple[float, bool, str]:
    """Return a value only when Yahoo reports it for the expected annual period."""
    results = timeseries.get("result") or []
    wanted = set(type_names)

    for item in results:
        types = item.get("meta", {}).get("type") or []
        matched_types = [type_name for type_name in types if type_name in wanted]
        for type_name in matched_types:
            values = item.get(type_name) or []
            for entry in reversed(values):
                if entry.get("asOfDate") != expected_date:
                    continue
                raw = _raw_value(entry.get("reportedValue"))
                if raw == raw:
                    return raw, True, entry.get("asOfDate") or ""
    return 0.0, False, ""


def _keyword_matches(text: str, keyword: str) -> bool:
    """Return whether a prohibited keyword matches without known false positives."""
    if keyword in {"alcohol", "alcoholic"} and (
        "non-alcohol" in text or "non alcoholic" in text or "nonalcohol" in text
    ):
        return False
    if keyword == "alcoholic beverages" and (
        "non-alcoholic beverages" in text
        or "non alcoholic beverages" in text
        or "nonalcoholic beverages" in text
    ):
        return False
    return keyword in text


def _qualitative_screen(sector: str, industry: str, description: str) -> tuple[bool, str]:
    """Run the prohibited activity screen for business sector and industry."""
    sector_lower = _normalize_text(sector)
    industry_lower = _normalize_text(industry)
    description_lower = _normalize_text(description)

    for prohibited in PROHIBITED_INDUSTRIES:
        if prohibited in industry_lower:
            return False, f"Prohibited industry: {industry}"

    sector_industry_text = f"{sector_lower} {industry_lower}"
    for keyword in PROHIBITED_KEYWORDS:
        if not _keyword_matches(sector_industry_text, keyword):
            continue
        if keyword == "gaming" and "electronic gaming" in sector_industry_text:
            continue
        return False, f"Prohibited activity keyword detected: {keyword}"

    for keyword in PROHIBITED_DESCRIPTION_KEYWORDS:
        if _keyword_matches(description_lower, keyword):
            return False, f"Prohibited activity described: {keyword}"

    return True, ""


def _quantitative_screen(
    market_cap: float,
    total_debt: float,
    cash_and_securities: float,
    accounts_receivable: float,
) -> tuple[bool, float, float, float, list[str]]:
    """Run AAOIFI financial ratio checks against market capitalization."""
    if market_cap <= 0:
        return False, 0.0, 0.0, 0.0, ["Market cap unavailable; cannot compute ratios"]

    debt_ratio = total_debt / market_cap
    cash_ratio = cash_and_securities / market_cap
    receivables_ratio = accounts_receivable / market_cap
    failed: list[str] = []

    if debt_ratio >= DEBT_THRESHOLD:
        failed.append(f"Debt ratio {debt_ratio * 100:.1f}% >= 30% threshold")
    if cash_ratio >= CASH_THRESHOLD:
        failed.append(f"Cash/securities ratio {cash_ratio * 100:.1f}% >= 30% threshold")
    if receivables_ratio >= RECEIVABLES_THRESHOLD:
        failed.append(f"Receivables ratio {receivables_ratio * 100:.1f}% >= 30% threshold")

    return not failed, debt_ratio, cash_ratio, receivables_ratio, failed


def _purification_rate(interest_income: float, total_revenue: float) -> float:
    """Calculate purification rate as non-compliant income over total revenue."""
    if total_revenue <= 0 or interest_income <= 0:
        return 0.0
    return min(interest_income / total_revenue, 1.0)


def screen_shariah(symbol: str) -> dict:
    """Screen one stock ticker for AAOIFI Shariah compliance."""
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        return {"error": "No symbol provided."}

    result = ShariahResult(symbol=normalized_symbol, name="", sector="", industry="")

    try:
        quote_summary = _fetch_quote_summary(normalized_symbol)
        profile = quote_summary.get("assetProfile") or {}
        price = quote_summary.get("price") or {}
        financial_data = quote_summary.get("financialData") or {}
        timeseries = _fetch_timeseries(normalized_symbol)

        result.name = price.get("longName") or price.get("shortName") or normalized_symbol
        result.sector = profile.get("sector") or ""
        result.industry = profile.get("industry") or ""
        quote_type = (price.get("quoteType") or "").upper()
        if quote_type and quote_type != "EQUITY":
            return {
                "symbol": normalized_symbol,
                "name": result.name,
                "quote_type": quote_type,
                "error": "Shariah screening currently supports individual equities only.",
                "verdict": "UNABLE TO SCREEN",
                "disclaimer": "Not a fatwa. Consult a qualified Shariah scholar before investing.",
            }
        result.market_cap = _raw_value(price.get("marketCap"))

        passed, reason = _qualitative_screen(
            result.sector,
            result.industry,
            profile.get("longBusinessSummary") or "",
        )
        result.sector_screen_passed = passed
        result.sector_screen_reason = reason

        result.total_debt, debt_available, _ = _latest_timeseries_value(
            timeseries,
            "annualTotalDebt",
        )
        if not debt_available:
            result.total_debt = _raw_value(financial_data.get("totalDebt"))
            if result.total_debt <= 0:
                result.warnings.append("Total debt unavailable; ratio may be incomplete.")

        result.cash_and_securities, cash_available, _ = _latest_timeseries_value(
            timeseries,
            "annualCashCashEquivalentsAndShortTermInvestments",
        )
        if not cash_available:
            result.cash_and_securities = _raw_value(financial_data.get("totalCash"))
            if result.cash_and_securities <= 0:
                result.warnings.append("Cash and securities unavailable; ratio may be incomplete.")

        result.accounts_receivable, receivables_available, _ = _latest_timeseries_value(
            timeseries,
            "annualAccountsReceivable",
            "annualNetReceivables",
        )
        if not receivables_available:
            result.warnings.append("Accounts receivable unavailable; ratio may be incomplete.")

        result.total_revenue, revenue_available, revenue_date = _latest_timeseries_value(
            timeseries,
            "annualTotalRevenue",
        )
        if not revenue_available:
            result.total_revenue = _raw_value(financial_data.get("totalRevenue"))
            result.warnings.append(
                "Annual revenue unavailable; using Yahoo financialData totalRevenue if present."
            )

        (
            result.interest_income,
            result.interest_income_available,
            interest_date,
        ) = _matching_period_value(
            timeseries,
            revenue_date,
            "annualInterestIncome",
            "annualInterestIncomeNonOperating",
        )
        if not result.interest_income_available:
            result.warnings.append(
                "Interest income unavailable; purification rate cannot be calculated."
            )
        elif revenue_date and interest_date and interest_date != revenue_date:
            result.interest_income = 0.0
            result.interest_income_available = False
            result.warnings.append(
                "Interest income period does not match annual revenue period; purification rate cannot be calculated."
            )

        (
            result.quantitative_passed,
            result.debt_ratio,
            result.cash_ratio,
            result.receivables_ratio,
            result.failed_ratios,
        ) = _quantitative_screen(
            result.market_cap,
            result.total_debt,
            result.cash_and_securities,
            result.accounts_receivable,
        )
        if result.market_cap <= 0:
            result.warnings.append(
                "Market cap not found. Try a Yahoo Finance ticker format such as THYAO.IS."
            )

        result.purification_rate = _purification_rate(
            result.interest_income,
            result.total_revenue,
        )
        result.compliant = result.sector_screen_passed and result.quantitative_passed

        if not result.sector_screen_passed:
            result.verdict = "HARAM - prohibited business activity"
        elif not result.quantitative_passed:
            result.verdict = "HARAM - financial ratios exceed AAOIFI thresholds"
        elif result.purification_rate > 0:
            result.verdict = (
                "HALAL with purification - donate "
                f"{result.purification_rate * 100:.2f}% of income to charity"
            )
        elif not result.interest_income_available:
            result.verdict = "HALAL - purification data unavailable"
        else:
            result.verdict = "HALAL - no purification required"
    except Exception as exc:
        logger.exception("Shariah screening failed for %s", normalized_symbol)
        return {
            "symbol": normalized_symbol,
            "error": f"Screening failed: {exc}",
            "verdict": "UNABLE TO SCREEN",
            "disclaimer": "Not a fatwa. Consult a qualified Shariah scholar before investing.",
        }

    return result.to_dict()


def screen_shariah_bulk(symbols: list[str]) -> dict:
    """Screen multiple stock tickers for AAOIFI Shariah compliance."""
    cleaned_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not cleaned_symbols:
        return {"error": "No symbols provided."}
    if len(cleaned_symbols) > MAX_BULK_SYMBOLS:
        return {"error": f"Maximum {MAX_BULK_SYMBOLS} symbols per bulk request."}

    results: dict[str, dict] = {}
    halal: list[str] = []
    haram: list[str] = []
    errors: list[str] = []

    for symbol in cleaned_symbols:
        report = screen_shariah(symbol)
        results[symbol] = report
        if "error" in report:
            errors.append(symbol)
        elif report.get("compliant"):
            halal.append(symbol)
        else:
            haram.append(symbol)

    return {
        "summary": {
            "total_screened": len(cleaned_symbols),
            "halal": len(halal),
            "haram": len(haram),
            "errors": len(errors),
            "halal_list": halal,
            "haram_list": haram,
            "compliant": len(halal),
            "non_compliant": len(haram),
            "compliant_list": halal,
            "non_compliant_list": haram,
            "error_list": errors,
        },
        "methodology": "AAOIFI Standard No. 21",
        "results": results,
        "disclaimer": "For informational purposes only. Not a fatwa.",
    }
