"""Unit tests for the FXMacroData release-calendar service.

httpx is mocked with ``httpx.MockTransport`` so no request leaves the process.
"""
from __future__ import annotations

import httpx
import pytest

from tradingview_mcp.core.errors import is_error
from tradingview_mcp.core.services import fxmacrodata_service
from tradingview_mcp.core.services.fxmacrodata_service import get_release_calendar

PAYLOAD = {
    "currency": "USD",
    "timezone": "UTC",
    "data_quality": {"source": "official"},
    "data": [
        {"indicator": "inflation", "market_tier": 1},
        {"indicator": "retail_sales", "market_tier": 2},
        {"indicator": "trade_balance", "market_tier": 3},
        {"indicator": "unknown_tier", "market_tier": "n/a"},
        {"indicator": "missing_tier"},
    ],
}


@pytest.fixture
def mock_http(monkeypatch):
    """Route the service's AsyncClient through a MockTransport handler."""
    calls: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def install(handler):
        def recording(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(recording)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(fxmacrodata_service.httpx, "AsyncClient", factory)
        return calls

    monkeypatch.delenv("FXMACRODATA_API_KEY", raising=False)
    return install


async def test_happy_path_returns_events(mock_http):
    calls = mock_http(lambda req: httpx.Response(200, json=PAYLOAD))

    result = await get_release_calendar("USD", limit=10)

    assert not is_error(result)
    assert result["currency"] == "USD"
    assert result["timezone"] == "UTC"
    assert result["data_quality"] == {"source": "official"}
    assert len(result["events"]) == 5
    assert calls[0].url.path == "/v1/calendar/usd"
    assert calls[0].url.params["limit"] == "10"
    assert "X-API-Key" not in calls[0].headers


async def test_api_key_sent_when_configured(mock_http, monkeypatch):
    calls = mock_http(lambda req: httpx.Response(200, json=PAYLOAD))
    monkeypatch.setenv("FXMACRODATA_API_KEY", "test-key")

    await get_release_calendar("eur")

    assert calls[0].headers["X-API-Key"] == "test-key"
    assert calls[0].url.path == "/v1/calendar/eur"


@pytest.mark.parametrize(
    "min_tier, expected",
    [
        (1, ["inflation"]),
        (2, ["inflation", "retail_sales"]),
        (3, ["inflation", "retail_sales", "trade_balance"]),
    ],
)
async def test_min_tier_filters_and_skips_non_numeric_tiers(mock_http, min_tier, expected):
    mock_http(lambda req: httpx.Response(200, json=PAYLOAD))

    result = await get_release_calendar("usd", min_tier=min_tier)

    assert [e["indicator"] for e in result["events"]] == expected


async def test_min_tier_none_keeps_everything(mock_http):
    mock_http(lambda req: httpx.Response(200, json=PAYLOAD))

    result = await get_release_calendar("usd", min_tier=None)

    assert len(result["events"]) == 5


@pytest.mark.parametrize("currency", ["us", "usdx", "us1", "../x", "", "u d"])
async def test_invalid_currency_rejected_without_request(mock_http, currency):
    calls = mock_http(lambda req: httpx.Response(200, json=PAYLOAD))

    result = await get_release_calendar(currency)

    assert is_error(result)
    assert result["error"]["code"] == "INVALID_PARAMETER"
    assert result["error"]["retryable"] is False
    assert calls == []


async def test_rate_limit_is_retryable_with_retry_after(mock_http):
    mock_http(lambda req: httpx.Response(429, headers={"Retry-After": "30"}))

    result = await get_release_calendar("usd")

    assert is_error(result)
    assert result["error"]["code"] == "UPSTREAM_RATE_LIMIT"
    assert result["error"]["retryable"] is True
    assert result["error"]["retry_after_s"] == 30


async def test_server_error_is_retryable(mock_http):
    mock_http(lambda req: httpx.Response(503))

    result = await get_release_calendar("usd")

    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["status_code"] == 503
    assert result["error"]["retryable"] is True


async def test_client_error_is_not_retryable(mock_http):
    mock_http(lambda req: httpx.Response(403))

    result = await get_release_calendar("eur")

    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["status_code"] == 403
    assert result["error"]["retryable"] is False


async def test_timeout_is_retryable(mock_http):
    def handler(req):
        raise httpx.ReadTimeout("timed out", request=req)

    mock_http(handler)

    result = await get_release_calendar("usd")

    assert result["error"]["code"] == "UPSTREAM_TIMEOUT"
    assert result["error"]["retryable"] is True


async def test_connection_error_is_retryable(mock_http):
    def handler(req):
        raise httpx.ConnectError("refused", request=req)

    mock_http(handler)

    result = await get_release_calendar("usd")

    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["retryable"] is True


async def test_non_json_body_returns_error(mock_http):
    mock_http(lambda req: httpx.Response(200, text="<html>oops</html>"))

    result = await get_release_calendar("usd")

    assert result["error"]["code"] == "UPSTREAM_ERROR"
