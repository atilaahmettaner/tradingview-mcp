#!/usr/bin/env python3
"""
CLI wrapper for tradingview-mcp — called by OpenClaw agent via bash.

Usage:
    python3 trading.py price AAPL
    python3 trading.py snapshot
    python3 trading.py backtest AAPL rsi 1y
    python3 trading.py backtest BTC-USD bollinger 6mo 1h
    python3 trading.py compare AAPL 2y
    python3 trading.py walkforward AAPL rsi 2y
    python3 trading.py sentiment BTC

Install path: ~/.openclaw/tools/trading.py
"""
import sys
import json
import os

# Auto-discover site-packages for tradingview-mcp-server
SITE_PACKAGES = "/root/.local/share/uv/tools/tradingview-mcp-server/lib/python3.12/site-packages"
if os.path.exists(SITE_PACKAGES):
    sys.path.insert(0, SITE_PACKAGES)
else:
    # Fallback: search common uv paths
    import glob
    candidates = glob.glob(
        os.path.expanduser(
            "~/.local/share/uv/tools/tradingview-mcp-server/lib/python*/site-packages"
        )
    )
    if candidates:
        sys.path.insert(0, candidates[0])

try:
    from tradingview_mcp.core.services.yahoo_finance_service import get_price, get_market_snapshot
    from tradingview_mcp.core.services.backtest_service import run_backtest, compare_strategies, walk_forward_backtest
    from tradingview_mcp.core.services.sentiment_service import analyze_sentiment
except ImportError as e:
    print(json.dumps({"error": str(e), "fix": "Run: uv tool install tradingview-mcp-server"}))
    sys.exit(1)

cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
args = sys.argv[2:]


def _require_symbol():
    """Return the first positional (symbol) argument.

    Emits a clear operator-facing error and exits non-zero when it is missing,
    instead of letting ``args[0]`` raise an opaque IndexError.
    """
    if not args:
        print(json.dumps({
            "error": f"Missing required symbol argument for '{cmd}'. "
                     f"Run 'trading.py help' for usage."
        }))
        sys.exit(1)
    return args[0]


try:
    if cmd == "price":
        print(json.dumps(get_price(_require_symbol()), indent=2))

    elif cmd == "snapshot":
        print(json.dumps(get_market_snapshot(), indent=2))

    elif cmd == "backtest":
        symbol   = _require_symbol()
        strategy = args[1] if len(args) > 1 else "rsi"
        period   = args[2] if len(args) > 2 else "1y"
        interval = args[3] if len(args) > 3 else "1d"
        print(json.dumps(run_backtest(symbol, strategy, period, interval=interval), indent=2))

    elif cmd == "compare":
        symbol = _require_symbol()
        period = args[1] if len(args) > 1 else "1y"
        print(json.dumps(compare_strategies(symbol, period), indent=2))

    elif cmd == "walkforward":
        symbol   = _require_symbol()
        strategy = args[1] if len(args) > 1 else "rsi"
        period   = args[2] if len(args) > 2 else "2y"
        print(json.dumps(walk_forward_backtest(symbol, strategy, period), indent=2))

    elif cmd == "sentiment":
        print(json.dumps(analyze_sentiment(_require_symbol()), indent=2))

    elif cmd == "help":
        print("Commands: price <sym> | snapshot | backtest <sym> <strategy> <period> [interval] | compare <sym> [period] | walkforward <sym> [strategy] [period] | sentiment <sym>")
        print("Strategies: rsi | bollinger | macd | ema_cross | supertrend | donchian")

    else:
        print(json.dumps({"error": f"Unknown command: {cmd}"}))

except Exception as e:
    print(json.dumps({"error": str(e)}))
