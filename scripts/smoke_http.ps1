# Smoke test: hit the streamable-http MCP server and list registered tools.
# Verifies that the 9 new tools (fundamentals, risk, thesis) loaded cleanly.

$ErrorActionPreference = "Stop"
$endpoint = "http://127.0.0.1:8000/mcp"

# Step 1: initialize an MCP session
$initBody = @{
    jsonrpc = "2.0"
    id      = 1
    method  = "initialize"
    params  = @{
        protocolVersion = "2024-11-05"
        capabilities    = @{}
        clientInfo      = @{ name = "smoke-script"; version = "0.1" }
    }
} | ConvertTo-Json -Depth 10 -Compress

$headers = @{
    "Content-Type" = "application/json"
    "Accept"       = "application/json, text/event-stream"
}

$response = Invoke-WebRequest -Uri $endpoint -Method Post -Body $initBody -Headers $headers
$sessionId = $response.Headers["Mcp-Session-Id"] | Select-Object -First 1
if (-not $sessionId) { Write-Error "no session id returned"; exit 1 }
Write-Output "session: $sessionId"

# Step 2: send initialized notification (required handshake)
$initializedBody = @{ jsonrpc = "2.0"; method = "notifications/initialized" } | ConvertTo-Json -Compress
$headersWithSession = $headers + @{ "Mcp-Session-Id" = $sessionId }
Invoke-WebRequest -Uri $endpoint -Method Post -Body $initializedBody -Headers $headersWithSession | Out-Null

# Step 3: list tools
$listBody = @{ jsonrpc = "2.0"; id = 2; method = "tools/list" } | ConvertTo-Json -Compress
$resp = Invoke-WebRequest -Uri $endpoint -Method Post -Body $listBody -Headers $headersWithSession
$body = $resp.Content

# Streamable HTTP can return SSE format. Strip the SSE wrapper if present.
if ($body -match "^data: (.+)$") {
    $body = $Matches[1]
}
# Sometimes there are multiple SSE frames; grab the last "data:" line
$dataLines = $body -split "`n" | Where-Object { $_ -match "^data: " } | ForEach-Object { $_ -replace "^data: ", "" }
if ($dataLines) { $body = $dataLines[-1] }

$parsed = $body | ConvertFrom-Json
$tools = $parsed.result.tools | ForEach-Object { $_.name } | Sort-Object

Write-Output ""
Write-Output "=== Registered tools ($($tools.Count)) ==="
$tools | ForEach-Object { Write-Output "  $_" }

$expectedNew = @(
    "stock_fundamentals", "compare_peers", "dividend_info",
    "position_sizing", "risk_reward_calc", "kelly_position_size",
    "correlation_matrix", "value_at_risk_analysis", "investment_thesis"
)
$missing = $expectedNew | Where-Object { $_ -notin $tools }
Write-Output ""
if ($missing) {
    Write-Output "FAIL: missing tools: $($missing -join ', ')"
    exit 1
} else {
    Write-Output "PASS: all 9 new tools registered"
}
