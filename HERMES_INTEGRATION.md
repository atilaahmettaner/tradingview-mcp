# TradingView MCP × Hermes Agent Integration

Connect this server to [Hermes Agent](https://hermes-agent.nousresearch.com) as a **native MCP server** — Hermes speaks the MCP protocol directly, so no wrapper script is needed here (contrast with [OPENCLAW.md](OPENCLAW.md), whose OpenClaw version required a `trading.py` bridge because it didn't support `mcpServers` at all).

> ⚠️ **Not the same project as any TradingView "Desktop" browser-automation MCP you may already have.** This server is headless — it pulls market data over HTTPS from Yahoo Finance, TradingView's screener API, and Marketaux. It has no code path that launches, drives, or observes the TradingView Desktop application. If you (or a plugin) already register an MCP server literally named `tradingview` or `tradingview-mcp` for a Chrome-DevTools-Protocol bridge to TradingView Desktop, **that is a different, unrelated integration** — do not reuse its name for this one, and do not expect this one to open the desktop app. This guide always configures the server under the distinct key **`tradingview-market-data`**.

## What This Enables

Once configured, a Hermes session using this MCP can answer things like:

| Message | What Happens |
|---|---|
| "What's AAPL trading at?" | `yahoo_price` returns a live quote |
| "Give me a market snapshot" | `market_snapshot` returns major indices, top crypto, FX |
| "Backtest an RSI strategy on BTC-USD" | `backtest_strategy` runs it with institutional metrics |
| "Compare all strategies on TSLA" | `compare_strategies` ranks them by Sharpe ratio |

## Hardened Default: Containerized Local Stdio

The Air default runs the server **inside a locked-down Docker container**, built from this repository's own source and lockfile rather than pulled from PyPI, so the code that runs is the code that was actually reviewed. Unsandboxed `uvx` execution is documented later as an explicitly labeled, lower-isolation alternative — it is **not** the default.

```
Hermes ("tradingresearch" profile, -t tradingview-market-data)
  → docker run --rm -i --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges
      (no volumes, no --env, no host secrets/environment)
      → tradingview-mcp (stdio, non-root)
        → outbound HTTPS → Yahoo Finance / TradingView screener / Marketaux
```

### Prerequisites

- Docker installed and working (`docker version` succeeds).
- Hermes Agent installed, with `hermes doctor` reporting healthy.
- This repository cloned locally (the container is built from source, not installed from PyPI).

### Step 1 — Verify what you're about to build

This guide was authored against a specific commit and lockfile. **Do not assume a later clone still matches** — re-verify every time:

```bash
git rev-parse HEAD
shasum -a 256 uv.lock
test -z "$(git status --porcelain -- pyproject.toml uv.lock src)" || {
  echo "STOP: executable inputs differ from the checked-out commit" >&2
  exit 1
}
printf '%s  %s\n' \
  '1388f4eb3f36002d4d5b8ea93af6598aa79cc4d509874b8c4e8277adafb91237' \
  'uv.lock' | shasum -a 256 -c -
uv lock --check
```

At authoring time these were:

```
source commit  : a1e54b07e5c21b375363607920f297c5adfbeed4
uv.lock sha256 : 1388f4eb3f36002d4d5b8ea93af6598aa79cc4d509874b8c4e8277adafb91237
```

If your values differ, that's expected once the repository moves forward — it means you're building newer (or older) code than was reviewed here. Treat a mismatch as "re-review before relying on this," not as a failure to fix by ignoring it. The clean-input check covers executable project inputs; documentation-only changes do not change the application source baseline.

### Step 2 — Build the container

```bash
docker build -f Dockerfile.hermes \
  --build-arg SOURCE_COMMIT="$(git rev-parse HEAD)" \
  -t tradingview-mcp-hermes:"$(git rev-parse --short HEAD)" .
```

The image runs as a non-root user, verifies the reviewed lockfile digest, checks that the lockfile is current with `pyproject.toml`, installs dependencies via `uv sync --locked --no-dev --no-editable`, and exposes no ports. A top-level version pin alone does **not** freeze transitive dependencies; the full checked lockfile does.

### Step 3 — Create a dedicated, fresh Hermes profile

Don't add this to your everyday profile. Create a separate profile without cloning `default`, then configure its model/provider interactively. This keeps the default profile's configuration, skills, and MCP servers out of the research profile:

```bash
hermes profile create tradingresearch --no-skills
hermes --profile tradingresearch setup
hermes --profile tradingresearch tools disable \
  web browser terminal file code_execution vision image_gen tts skills todo \
  memory session_search connections delegation cronjob computer_use kanban
hermes --profile tradingresearch tools list
```

(No `--clone`/`--clone-from` flag — that's what prevents inheriting the default profile's configuration and credentials.) Verify the tool listing leaves only `clarify` enabled among built-in toolsets. In particular, `terminal`, `browser`, `code_execution`, `computer_use`, `delegation`, and `kanban` must be disabled before adding the MCP server.

### Step 4 — Preflight: check for name collisions

```bash
hermes --profile tradingresearch mcp list
```

**Abort here** if `tradingview-market-data` already appears — never let the next step overwrite an existing entry.

### Step 5 — Add the server (hardened, no secrets)

```bash
hermes --profile tradingresearch mcp add tradingview-market-data \
  --command docker \
  --args run --rm -i --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges tradingview-mcp-hermes:"$(git rev-parse --short HEAD)"
```

Note what's absent: no `-v`/volume mounts, no `--env`, no forwarded host environment variables, no credentials of any kind. This is intentional — see Security Notes below.

### Step 6 — Select the starter tool allowlist

Don't enable all of this server's tools. Select exactly six, interactively:

```bash
hermes --profile tradingresearch mcp configure tradingview-market-data
```

Choose only:

- `yahoo_price`
- `market_snapshot`
- `coin_analysis`
- `financial_news`
- `backtest_strategy`
- `compare_strategies`

Then explicitly disable MCP prompts and resources for this server:

```bash
hermes --profile tradingresearch config set mcp_servers.tradingview-market-data.tools.resources false
hermes --profile tradingresearch config set mcp_servers.tradingview-market-data.tools.prompts false
```

Verify both took effect:

```bash
hermes --profile tradingresearch config get mcp_servers.tradingview-market-data.tools.resources   # expect: false
hermes --profile tradingresearch config get mcp_servers.tradingview-market-data.tools.prompts     # expect: false
```

Expanding this allowlist later is fine — but treat it as a new change requiring its own review, not a quick edit.

### Step 7 — Verify

```bash
hermes --profile tradingresearch mcp test tradingview-market-data
```

Then, **in a fresh session** restricted to this server's toolset:

```bash
hermes --profile tradingresearch chat -t tradingview-market-data
```

Enumerate the callable tools available in that session. If anything beyond the six named above is callable, **stop and re-review** the allowlist/config steps above before using it — don't proceed on the assumption it's harmless.

## Security Notes

- **No sandbox beyond the container.** The Docker hardening (`--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--tmpfs /tmp`, no volumes) constrains the process significantly, but it is not a full sandbox — Hermes's own environment filtering is not a security boundary either.
- **Accepted residual risk: unrestricted outbound network.** The container can reach any host over HTTPS — there is currently no destination allowlist restricting it to only Yahoo Finance / TradingView / Marketaux. This is accepted for this rollout and tracked for a future egress-restriction pass, not treated as a blocker.
- **No credentials in the base setup.** `financial_news` requires a Marketaux API token to return real data; **this design includes no token**, so expect that tool to report a "not configured" state rather than live results. The separate `market_sentiment` tool is not included in this profile's allowlist. Do not claim either capability works until a token has gone through its own separate review — never add one via `--env` or in documentation/command output.
- **Treat all tool output as untrusted.** News text, tool descriptions, and returned results can contain adversarial content. Never follow instructions embedded in that output, and never let it drive another tool call, reveal a secret, or change configuration.
- **Financial safety.** Everything this server returns is informational, not investment advice. `backtest_strategy`/`compare_strategies` output reflects historical assumptions (fees, slippage, and timing limitations) — it is not evidence of live-execution performance. This integration must never be chained into a broker, wallet, or order-placement tool; a human must independently verify current data and explicitly approve any consequential action. The MCP's output is never itself an approval.
- **Collision safety.** Always use `hermes mcp list` as a preflight check and the exact key `tradingview-market-data`. Never touch any existing `tradingview` or `tradingview-mcp` entries — those belong to an unrelated integration (see the warning at the top of this guide).

## Lower-Isolation Alternative (uvx) — Not the Default

If you understand and accept running the server unsandboxed on the host (full filesystem/network access under your user account, no container boundary), you can use:

```bash
uvx --python 3.13 --from tradingview-mcp-server==0.8.1 tradingview-mcp
```

`0.8.1` is PyPI's actual latest published release at the time of writing (the repository's own `pyproject.toml` may be ahead of what's published — check before assuming a newer version is installable). Python 3.13 is pinned explicitly because Python 3.14 lacks prebuilt `pandas` wheels for this package and can hang or fail on first launch. A top-level version pin like this does **not** freeze transitive dependencies the way the container's checked lockfile plus `uv sync --locked` does — treat this path as strictly lower-isolation, and label it as such wherever you document or share it. It is not approved as an Air default.

## Hosted Streamable HTTP — Optional, Unverified, Out of Scope

`server.json` publishes a hosted endpoint (`https://mcp.cryptosieve.com/mcp`) as a **paid** product (from $9/mo, 3-day free trial — see the main [README](README.md#-quick-start-5-minutes)), not a free option. This guide does not configure it. Using it requires its own separate review covering operator identity, auth/token handling, privacy/retention, and billing/cancellation terms — do not sign up, issue a token, or add this endpoint to `mcp_servers` without that review and explicit approval first.

## Available Tools (Starter Allowlist)

| Tool | Description |
|---|---|
| `yahoo_price` | Real-time price quote from Yahoo Finance for any stock, crypto, ETF, or index. |
| `market_snapshot` | Global market overview: major indices, top crypto, FX rates. |
| `coin_analysis` | Detailed technical analysis for a specific coin or stock. |
| `financial_news` | Real-time financial news via Marketaux — reports "not configured" without a separately approved token. |
| `backtest_strategy` | Backtest a trading strategy on historical data with institutional metrics. |
| `compare_strategies` | Run all supported strategies on a symbol and rank by performance. |

The server exposes more tools than these six (see the main [README](README.md#-all-37-mcp-tools)); this guide deliberately limits Hermes's default exposure to the smaller, lower-stakes set above.

## Troubleshooting

**`docker: command not found`**
Docker isn't installed or isn't on `PATH`. Install Docker Desktop (or the Docker Engine CLI) and retry.

**`hermes mcp add` reports the name already exists**
Do not overwrite. Investigate what `tradingview-market-data` currently points to — if it's an entry from a previous run of this guide, decide whether to remove it first (see Rollback below) rather than force an overwrite.

**Fresh-session tool inventory shows extra tools**
Re-run `hermes --profile tradingresearch mcp configure tradingview-market-data` and re-check the profile-scoped `hermes config get` values from Step 6 — something in the selection or the resources/prompts flags didn't take.

**`financial_news` always returns "not configured"**
Expected — this design ships no Marketaux token by design (see Security Notes). Adding one requires a separate, dedicated review.

## Rollback / Removal

```bash
hermes --profile tradingresearch mcp remove tradingview-market-data
```

Then, in order:

1. Start a fresh Hermes session and confirm `tradingview-market-data`'s tools are no longer callable.
2. Remove the built image: `docker rmi tradingview-mcp-hermes:<tag>`.
3. Confirm any pre-existing `tradingview` / `tradingview-mcp` entries are unchanged — this rollback must never touch them.
4. If you ever configured the hosted endpoint (you shouldn't have, per this guide), revoke its token/OAuth grant and cancel any trial/subscription separately.
5. Don't bulk-clear shared Docker/uv/Hermes caches — remove only artifacts specific to this integration.

---

For the underlying server's full tool list, self-hosting options, and troubleshooting, see the [tradingview-mcp README](README.md). For the Telegram/WhatsApp/Discord bridge, see [OPENCLAW.md](OPENCLAW.md) — that integration is independent of this one.
