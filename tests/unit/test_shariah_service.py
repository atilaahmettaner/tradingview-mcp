from unittest.mock import MagicMock

import pytest

from tradingview_mcp.core.services import shariah_service
from tradingview_mcp.core.services.shariah_service import (
    DEBT_THRESHOLD,
    _purification_rate,
    _qualitative_screen,
    _quantitative_screen,
    _safe_float,
    screen_shariah,
    screen_shariah_bulk,
)


def _raw(value: float) -> dict:
    return {"raw": value, "fmt": str(value)}


def _make_quote_summary(
    long_name: str = "Test Corp",
    sector: str = "Technology",
    industry: str = "Software-Application",
    market_cap: float = 3_000_000_000_000,
    total_debt: float = 500_000_000_000,
    total_cash: float = 200_000_000_000,
    total_revenue: float = 400_000_000_000,
    quote_type: str = "EQUITY",
) -> dict:
    return {
        "assetProfile": {
            "sector": sector,
            "industry": industry,
            "longBusinessSummary": f"{long_name} makes software.",
        },
        "price": {
            "longName": long_name,
            "shortName": long_name,
            "marketCap": _raw(market_cap),
            "quoteType": quote_type,
        },
        "financialData": {
            "totalDebt": _raw(total_debt),
            "totalCash": _raw(total_cash),
            "totalRevenue": _raw(total_revenue),
        },
    }


def _make_timeseries(
    total_debt: float = 500_000_000_000,
    cash_and_securities: float = 200_000_000_000,
    receivables: float = 100_000_000_000,
    total_revenue: float = 400_000_000_000,
    interest_income: float = 1_000_000_000,
    include_interest_income: bool = True,
    interest_income_nan: bool = False,
    revenue_date: str = "2025-12-31",
    interest_date: str | None = "2025-12-31",
) -> dict:
    def item(type_name: str, value: float, date: str) -> dict:
        return {
            "meta": {"type": [type_name]},
            type_name: [
                {
                    "asOfDate": date,
                    "reportedValue": _raw(value),
                }
            ],
        }

    result = [
        item("annualTotalDebt", total_debt, revenue_date),
        item(
            "annualCashCashEquivalentsAndShortTermInvestments",
            cash_and_securities,
            revenue_date,
        ),
        item("annualAccountsReceivable", receivables, revenue_date),
        item("annualTotalRevenue", total_revenue, revenue_date),
    ]
    if include_interest_income:
        result.append(
            item(
                "annualInterestIncome",
                float("nan") if interest_income_nan else interest_income,
                interest_date or revenue_date,
            )
        )
    return {"result": result}


def _mock_yahoo(monkeypatch, quote_summary: dict | None = None, timeseries: dict | None = None):
    monkeypatch.setattr(
        shariah_service,
        "_fetch_quote_summary",
        MagicMock(return_value=quote_summary or _make_quote_summary()),
    )
    monkeypatch.setattr(
        shariah_service,
        "_fetch_timeseries",
        MagicMock(return_value=timeseries or _make_timeseries()),
    )


def test_safe_float_handles_missing_and_invalid_values():
    assert _safe_float(3.14) == pytest.approx(3.14)
    assert _safe_float(None) == 0.0
    assert _safe_float(float("nan")) == 0.0
    assert _safe_float("N/A") == 0.0


def test_qualitative_screen_passes_clean_technology_company():
    passed, reason = _qualitative_screen(
        "Technology",
        "Software-Application",
        "Builds cloud software.",
    )

    assert passed is True
    assert reason == ""


def test_qualitative_screen_fails_prohibited_industry():
    passed, reason = _qualitative_screen(
        "Financial Services",
        "Banks-Regional",
        "Regional bank.",
    )

    assert passed is False
    assert "prohibited" in reason.lower()


def test_qualitative_screen_allows_video_gaming_industry():
    passed, reason = _qualitative_screen(
        "Communication Services",
        "Electronic Gaming & Multimedia",
        "Video game developer.",
    )

    assert passed is True
    assert reason == ""


def test_qualitative_screen_ignores_broad_credit_word_in_description():
    passed, reason = _qualitative_screen(
        "Technology",
        "Consumer Electronics",
        "The company offers payment, credit, and cloud services.",
    )

    assert passed is True
    assert reason == ""


def test_qualitative_screen_allows_non_alcoholic_beverages():
    passed, reason = _qualitative_screen(
        "Consumer Defensive",
        "Beverages - Non-Alcoholic",
        "The company makes nonalcoholic beverages, soft drinks, and bottled water.",
    )

    assert passed is True
    assert reason == ""


def test_qualitative_screen_fails_brewers_with_spaced_industry_hyphen():
    passed, reason = _qualitative_screen(
        "Consumer Defensive",
        "Beverages - Brewers",
        "The company produces beer.",
    )

    assert passed is False
    assert "prohibited" in reason.lower()


def test_qualitative_screen_fails_explicit_description_prohibited_activity():
    passed, reason = _qualitative_screen(
        "Consumer Cyclical",
        "Entertainment",
        "The company operates casino and sports betting platforms.",
    )

    assert passed is False
    assert "prohibited" in reason.lower()


def test_quantitative_screen_requires_all_ratios_below_threshold():
    passed, debt, cash, receivables, failed = _quantitative_screen(
        market_cap=1_000_000,
        total_debt=100_000,
        cash_and_securities=50_000,
        accounts_receivable=80_000,
    )

    assert passed is True
    assert debt == pytest.approx(0.1)
    assert cash == pytest.approx(0.05)
    assert receivables == pytest.approx(0.08)
    assert failed == []


def test_quantitative_screen_fails_at_threshold_boundary():
    threshold_value = int(1_000_000 * DEBT_THRESHOLD)

    passed, _, _, _, failed = _quantitative_screen(
        market_cap=1_000_000,
        total_debt=threshold_value,
        cash_and_securities=threshold_value,
        accounts_receivable=threshold_value,
    )

    assert passed is False
    assert len(failed) == 3
    assert all("30% threshold" in item for item in failed)


def test_quantitative_screen_passes_just_below_30_percent_threshold():
    passed, debt, cash, receivables, failed = _quantitative_screen(
        market_cap=1_000_000,
        total_debt=299_999,
        cash_and_securities=299_999,
        accounts_receivable=299_999,
    )

    assert passed is True
    assert debt == pytest.approx(0.299999)
    assert cash == pytest.approx(0.299999)
    assert receivables == pytest.approx(0.299999)
    assert failed == []


def test_quantitative_screen_fails_without_market_cap():
    passed, _, _, _, failed = _quantitative_screen(0, 0, 0, 0)

    assert passed is False
    assert any("market cap" in item.lower() for item in failed)


def test_purification_rate_is_interest_income_over_revenue():
    assert _purification_rate(1_000_000, 100_000_000) == pytest.approx(0.01)
    assert _purification_rate(0, 100_000_000) == 0.0
    assert _purification_rate(100, 0) == 0.0
    assert _purification_rate(999_999_999, 1) == 1.0


def test_screen_shariah_returns_compliant_report(monkeypatch):
    _mock_yahoo(monkeypatch)

    result = screen_shariah(" aapl ")

    assert result["symbol"] == "AAPL"
    assert result["status"] == "halal"
    assert result["compliant"] is True
    assert result["methodology"] == "AAOIFI Standard No. 21"
    assert result["purification"]["rate"] == "0.25%"
    assert result["purification"]["available"] is True


def test_screen_shariah_uses_financial_data_fallbacks(monkeypatch):
    _mock_yahoo(monkeypatch, timeseries={"result": []})

    result = screen_shariah("AAPL")

    assert result["symbol"] == "AAPL"
    assert result["raw_financials"]["total_debt"] == 500_000_000_000
    assert result["raw_financials"]["cash_and_securities"] == 200_000_000_000
    assert result["purification"]["available"] is False
    assert result["warnings"]


def test_screen_shariah_validates_empty_symbol():
    result = screen_shariah("  ")

    assert result == {"error": "No symbol provided."}


def test_screen_shariah_handles_yahoo_fetch_error(monkeypatch):
    monkeypatch.setattr(
        shariah_service,
        "_fetch_quote_summary",
        MagicMock(side_effect=Exception("Yahoo unavailable")),
    )

    result = screen_shariah("AAPL")

    assert result["symbol"] == "AAPL"
    assert "Yahoo unavailable" in result["error"]
    assert "disclaimer" in result


def test_screen_shariah_rejects_non_equity_quote_types(monkeypatch):
    _mock_yahoo(monkeypatch, quote_summary=_make_quote_summary(quote_type="ETF"))

    result = screen_shariah("SPY")

    assert result["symbol"] == "SPY"
    assert result["quote_type"] == "ETF"
    assert "individual equities" in result["error"]
    assert result["verdict"] == "UNABLE TO SCREEN"


def test_screen_shariah_fails_prohibited_business_activity(monkeypatch):
    _mock_yahoo(
        monkeypatch,
        quote_summary=_make_quote_summary(
            sector="Financial Services",
            industry="Banks-Regional",
        ),
    )

    result = screen_shariah("JPM")

    assert result["status"] == "haram"
    assert result["compliant"] is False
    assert result["screening"]["qualitative_screen"]["status"] == "FAILED"


def test_screen_shariah_handles_statement_fetch_warnings(monkeypatch):
    _mock_yahoo(monkeypatch, timeseries={"result": []})

    result = screen_shariah("ERR")

    assert result["symbol"] == "ERR"
    assert result["warnings"]


def test_screen_shariah_marks_purification_unavailable_when_interest_income_missing(monkeypatch):
    _mock_yahoo(monkeypatch, timeseries=_make_timeseries(include_interest_income=False))

    result = screen_shariah("AAPL")

    assert result["status"] == "halal"
    assert result["purification"]["available"] is False
    assert "unavailable" in result["purification"]["note"].lower()
    assert "purification data unavailable" in result["verdict"].lower()


def test_screen_shariah_marks_purification_unavailable_when_interest_income_nan(monkeypatch):
    _mock_yahoo(monkeypatch, timeseries=_make_timeseries(interest_income_nan=True))

    result = screen_shariah("AAPL")

    assert result["status"] == "halal"
    assert result["purification"]["available"] is False
    assert "unavailable" in result["purification"]["note"].lower()


def test_screen_shariah_marks_purification_unavailable_when_periods_mismatch(monkeypatch):
    _mock_yahoo(
        monkeypatch,
        timeseries=_make_timeseries(revenue_date="2025-12-31", interest_date="2024-12-31"),
    )

    result = screen_shariah("AAPL")

    assert result["status"] == "halal"
    assert result["purification"]["available"] is False
    assert "unavailable" in result["purification"]["note"].lower()


def test_screen_shariah_bulk_summarizes_results(monkeypatch):
    mock_screen = MagicMock(
        side_effect=[
            {"symbol": "AAPL", "compliant": True},
            {"symbol": "JPM", "compliant": False},
            {"symbol": "BAD", "error": "not found"},
        ]
    )
    monkeypatch.setattr(shariah_service, "screen_shariah", mock_screen)

    result = screen_shariah_bulk(["AAPL", "JPM", "BAD"])

    assert result["summary"]["total_screened"] == 3
    assert result["summary"]["halal"] == 1
    assert result["summary"]["haram"] == 1
    assert result["summary"]["halal_list"] == ["AAPL"]
    assert result["summary"]["haram_list"] == ["JPM"]
    assert result["summary"]["compliant"] == 1
    assert result["summary"]["non_compliant"] == 1
    assert result["summary"]["compliant_list"] == ["AAPL"]
    assert result["summary"]["non_compliant_list"] == ["JPM"]
    assert result["summary"]["errors"] == 1
    assert result["summary"]["error_list"] == ["BAD"]


def test_screen_shariah_bulk_validates_request_size():
    assert "error" in screen_shariah_bulk([])
    assert "20" in screen_shariah_bulk([f"SYM{i}" for i in range(21)])["error"]


def test_server_bulk_tool_parses_and_normalizes_symbols(monkeypatch):
    from tradingview_mcp import server

    mock_bulk = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(server, "screen_shariah_bulk", mock_bulk)

    result = server.check_shariah_compliance_bulk(" aapl, twse:taiex, , msft ")

    assert result == {"ok": True}
    mock_bulk.assert_called_once_with(["AAPL", "^TWII", "MSFT"])


def test_server_single_tool_normalizes_symbol(monkeypatch):
    from tradingview_mcp import server

    mock_screen = MagicMock(return_value={"status": "halal"})
    monkeypatch.setattr(server, "screen_shariah", mock_screen)

    result = server.check_shariah_compliance(" twse:taiex ")

    assert result == {"status": "halal"}
    mock_screen.assert_called_once_with("^TWII")
