"""Hermetic checks for the optional two-server MCP research example."""

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, TextContent

spec = importlib.util.spec_from_file_location(
    "market_research", Path(__file__).parents[2] / "examples" / "market_research.py"
)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


def test_payload_text_fallback_and_errors():
    assert example.tool_payload(
        CallToolResult(content=[TextContent(type="text", text='{"price": 123}')])
    ) == {"price": 123}
    with pytest.raises(RuntimeError, match="MCP tool failed"):
        example.tool_payload(
            CallToolResult(
                isError=True, content=[TextContent(type="text", text="rate limited")]
            )
        )
    with pytest.raises(RuntimeError, match="Provider failed"):
        example.tool_payload(
            CallToolResult(content=[], structuredContent={"error": "outage"})
        )
    with pytest.raises(TypeError, match="JSON object"):
        example.tool_payload(
            CallToolResult(content=[TextContent(type="text", text="[]")])
        )


@pytest.mark.parametrize(
    "failure", [None, "empty_search", "failed_fetch", "quote_error"]
)
async def test_research_dispatch_and_failures(monkeypatch, failure):
    calls = []
    transports = []

    @asynccontextmanager
    async def stdio(server):
        assert server.args == ["-m", "tradingview_mcp.server"]
        yield "market", None

    @asynccontextmanager
    async def http(url, **kwargs):
        transports.append((url, kwargs))
        yield "web", None, None

    class Session:
        def __init__(self, read, write, **kwargs):
            self.kind = read

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name=n) for n in ["web_search", "web_fetch"]]
            )

        async def call_tool(self, name, arguments):
            calls.append((self.kind, name, arguments))
            payload = {
                "yahoo_price": {"error": "quote unavailable"}
                if failure == "quote_error"
                else {"price": 123},
                "web_search": {
                    "results": []
                    if failure == "empty_search"
                    else [{"url": "https://example.org/earnings"}]
                },
                "web_fetch": {
                    "results": []
                    if failure == "failed_fetch"
                    else [{"excerpts": ["Revenue rose 5%."]}]
                },
            }[name]
            return CallToolResult(content=[], structuredContent=payload)

    monkeypatch.setattr(example, "stdio_client", stdio)
    monkeypatch.setattr(example, "streamablehttp_client", http)
    monkeypatch.setattr(example, "ClientSession", Session)
    question = "Apple earnings " + "revenue " * 30
    if failure:
        with pytest.raises(RuntimeError):
            await example.research("AAPL", question)
        assert (
            len(calls)
            == {"quote_error": 1, "empty_search": 2, "failed_fetch": 3}[failure]
        )
        return

    output = await example.research("AAPL", question)
    assert output["quote"] == {"price": 123}
    assert output["source"]["results"][0]["excerpts"] == ["Revenue rose 5%."]
    assert [call[:2] for call in calls] == [
        ("market", "yahoo_price"),
        ("web", "web_search"),
        ("web", "web_fetch"),
    ]
    assert calls[0][2] == {"symbol": "AAPL"}
    search_args, fetch_args = calls[1][2], calls[2][2]
    assert search_args["session_id"] == fetch_args["session_id"]
    assert len(search_args["session_id"]) == 36
    assert fetch_args["urls"] == ["https://example.org/earnings"]
    assert fetch_args["objective"] == question[:200]
    assert search_args["search_queries"] == fetch_args["search_queries"] == [question]
    assert transports == [
        (
            example.PARALLEL_URL,
            {
                "headers": {"User-Agent": example.USER_AGENT},
                "timeout": 30,
                "sse_read_timeout": 60,
            },
        )
    ]
