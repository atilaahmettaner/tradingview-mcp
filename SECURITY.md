# Security Policy

## Supported Versions

Only the latest minor release receives security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.9.x   | :white_check_mark: |
| < 0.9   | :x:                |

## Reporting a Vulnerability

Please report vulnerabilities privately via
[GitHub Security Advisories](https://github.com/atilaahmettaner/tradingview-mcp/security/advisories/new)
— do **not** open a public issue for security problems.

You can expect an acknowledgement within a week. If the report is accepted,
a fix will be released as a patch version and credited to you in the
changelog (unless you prefer otherwise).

## Scope notes

- This server holds no user credentials of its own; the only secrets it
  reads are optional API tokens from environment variables
  (`MARKETAUX_API_TOKEN`, `PROXY_*`). Never commit a `.env` file.
- All market data comes from third-party upstreams (TradingView, Yahoo
  Finance, Marketaux); treat tool output as informational, not as trading
  advice.
