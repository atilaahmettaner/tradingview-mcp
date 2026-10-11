"""Pair a TradingView MCP quote with anonymous Parallel web research."""

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from typing import Any
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

PARALLEL_URL = "https://search.parallel.ai/mcp"
USER_AGENT = "tradingview-mcp/market-research-example"
TIMEOUT = timedelta(seconds=60)


def tool_payload(result: CallToolResult) -> dict[str, Any]:
    """Decode a tool's JSON payload and surface protocol or provider errors."""
    if result.isError:
        details = "\n".join(
            block.text for block in result.content if block.type == "text"
        )
        raise RuntimeError(f"MCP tool failed: {details}")
    payload = result.structuredContent
    if payload is None:
        for block in result.content:
            if block.type == "text":
                try:
                    payload = json.loads(block.text)
                    break
                except json.JSONDecodeError:
                    continue
    if not isinstance(payload, dict):
        raise TypeError("MCP tool did not return a JSON object")
    if "error" in payload:
        raise RuntimeError(f"Provider failed: {payload['error']}")
    return payload


async def research(symbol: str, question: str) -> dict[str, Any]:
    """Get a quote, search the question, then fetch one matching source."""
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tradingview_mcp.server"],
        env=dict(os.environ),
    )
    async with (
        stdio_client(server) as (read, write),
        ClientSession(read, write, read_timeout_seconds=TIMEOUT) as market,
    ):
        await market.initialize()
        quote = tool_payload(await market.call_tool("yahoo_price", {"symbol": symbol}))

    session_id = str(uuid4())
    queries = [question]
    async with (
        streamablehttp_client(
            PARALLEL_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
            sse_read_timeout=60,
        ) as (read, write, _),
        ClientSession(read, write, read_timeout_seconds=TIMEOUT) as web,
    ):
        await web.initialize()
        tools = {tool.name for tool in (await web.list_tools()).tools}
        if not {"web_search", "web_fetch"}.issubset(tools):
            raise RuntimeError("Parallel MCP is missing search or fetch tools")
        search = tool_payload(
            await web.call_tool(
                "web_search",
                {
                    "objective": question,
                    "search_queries": queries,
                    "session_id": session_id,
                },
            )
        )
        results = search.get("results", [])
        if not results:
            raise RuntimeError("Web search returned no sources; try a broader question")
        source_url = results[0]["url"]
        source = tool_payload(
            await web.call_tool(
                "web_fetch",
                {
                    "urls": [source_url],
                    "objective": question[:200],
                    "search_queries": queries,
                    "session_id": session_id,
                },
            )
        )
        if not source.get("results"):
            raise RuntimeError(f"Source fetch failed: {source.get('errors', [])}")
    return {"quote": quote, "search": search, "source": source}


def error_message(exc: BaseException) -> str:
    """Expose nested MCP transport errors on Python 3.10 and newer."""
    children = getattr(exc, "exceptions", ())
    return (
        "; ".join(error_message(child) for child in children) if children else str(exc)
    )


def main() -> None:
    """Print research evidence as JSON without requiring a model or API key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Yahoo Finance symbol, e.g. AAPL or BTC-USD")
    parser.add_argument(
        "question", help="Research query, e.g. 'Apple latest earnings revenue'"
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(research(args.symbol, args.question))
    except Exception as exc:
        print(f"Market research failed: {error_message(exc)}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
