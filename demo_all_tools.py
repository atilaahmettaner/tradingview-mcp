#!/usr/bin/env python3
"""
Comprehensive demo of all TradingView MCP Server tools
"""

import sys
import json
sys.path.insert(0, "src")

from tradingview_mcp.server import (
    # Market Screening
    top_gainers,
    top_losers,
    bollinger_scan,
    rating_filter,
    # Technical Analysis
    coin_analysis,
    consecutive_candles_scan,
    advanced_candle_pattern,
    # Resources
    exchanges_list
)

def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def print_result(tool_name, result):
    print(f"🔧 Tool: {tool_name}")
    print("-" * 70)
    print(json.dumps(result, indent=2, default=str))
    print()

def main():
    print("🚀 TradingView MCP Server - Complete Tool Demonstration")
    print("=" * 70)

    # ========================================================================
    # CATEGORY 1: MARKET SCREENING TOOLS
    # ========================================================================
    print_section("📈 CATEGORY 1: MARKET SCREENING TOOLS")

    # Example 1: Top Gainers
    print("Example 1: Top Gainers on KuCoin (15m timeframe)")
    try:
        result = top_gainers(exchange="KUCOIN", timeframe="15m", limit=5)
        print_result("top_gainers", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    # Example 2: Top Losers
    print("Example 2: Top Losers on Binance (1h timeframe)")
    try:
        result = top_losers(exchange="BINANCE", timeframe="1h", limit=5)
        print_result("top_losers", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    # Example 3: Bollinger Band Squeeze Scan
    print("Example 3: Bollinger Band Squeeze Detection (BBW < 0.04)")
    try:
        result = bollinger_scan(exchange="KUCOIN", timeframe="4h", bbw_threshold=0.04, limit=5)
        print_result("bollinger_scan", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    # Example 4: Rating Filter (Strong Buy signals)
    print("Example 4: Filter by Bollinger Band Rating (Strong Buy = +2)")
    try:
        result = rating_filter(exchange="KUCOIN", timeframe="15m", rating=2, limit=5)
        print_result("rating_filter", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    # ========================================================================
    # CATEGORY 2: TECHNICAL ANALYSIS TOOLS
    # ========================================================================
    print_section("🔍 CATEGORY 2: TECHNICAL ANALYSIS TOOLS")

    # Example 5: Individual Coin Analysis
    print("Example 5: Deep Technical Analysis of Bitcoin (BTCUSDT)")
    try:
        result = coin_analysis(symbol="BTCUSDT", exchange="KUCOIN", timeframe="1h")
        print_result("coin_analysis", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    # Example 6: Consecutive Candles Pattern Scan
    print("Example 6: Find Coins with 3+ Consecutive Bullish Candles")
    try:
        result = consecutive_candles_scan(
            exchange="KUCOIN",
            timeframe="15m",
            pattern_type="bullish",
            candle_count=3,
            min_growth=2.0,
            limit=5
        )
        print_result("consecutive_candles_scan", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    # Example 7: Advanced Candle Pattern Analysis
    print("Example 7: Advanced Multi-Timeframe Candle Pattern Detection")
    try:
        result = advanced_candle_pattern(
            exchange="KUCOIN",
            base_timeframe="15m",
            pattern_length=3,
            min_size_increase=10.0,
            limit=5
        )
        print_result("advanced_candle_pattern", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    # ========================================================================
    # CATEGORY 3: INFORMATION & RESOURCES
    # ========================================================================
    print_section("📋 CATEGORY 3: INFORMATION & RESOURCES")

    # Example 8: List Available Exchanges
    print("Example 8: List All Supported Exchanges and Markets")
    try:
        result = exchanges_list()
        print_result("exchanges://list", result)
    except Exception as e:
        print(f"❌ Error: {e}\n")

    print("\n" + "=" * 70)
    print("✅ Demo Complete!")
    print("=" * 70)
    print("""
📝 Summary:
   • Market Screening: 4 tools for finding trading opportunities
   • Technical Analysis: 3 tools for deep market analysis
   • Resources: 1 resource for exchange information

🎯 All tools are ready to use with the MCP server!
""")

if __name__ == "__main__":
    main()
