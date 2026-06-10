#Confirm the docker image starting and use the below script to get price
#Sample:
#powershell -ExecutionPolicy Bypass -File .\call-yahoo-price.ps1 -Symbol AAPL
#powershell -ExecutionPolicy Bypass -File .\call-yahoo-price.ps1 -Symbol TSLA
#powershell -ExecutionPolicy Bypass -File .\call-yahoo-price.ps1 -Symbol BTC-USD

param(
  [string]$Symbol = "AAPL"
)

$MCP_URL = "http://127.0.0.1:8080/mcp"
$headers = @{
  "Content-Type" = "application/json"
  "Accept"       = "application/json, text/event-stream"
}

# 1. Initialize
$initBody = @{
  jsonrpc = "2.0"; id = 1; method = "initialize"
  params = @{
    protocolVersion = "2025-03-26"
    capabilities    = @{}
    clientInfo      = @{ name = "ps-client"; version = "1.0" }
  }
} | ConvertTo-Json -Depth 5

$r = Invoke-WebRequest -Uri $MCP_URL -Method POST -Headers $headers -Body $initBody -UseBasicParsing
$sessionId = $r.Headers["mcp-session-id"]
$headers["Mcp-Session-Id"] = $sessionId

# 2. Ready
Invoke-WebRequest -Uri $MCP_URL -Method POST -Headers $headers `
  -Body '{"jsonrpc":"2.0","method":"notifications/initialized"}' -UseBasicParsing | Out-Null

# 3. Call yahoo_price
$callBody = @{
  jsonrpc = "2.0"; id = 3; method = "tools/call"
  params = @{
    name      = "yahoo_price"
    arguments = @{ symbol = $Symbol }
  }
} | ConvertTo-Json -Depth 5

$result = Invoke-WebRequest -Uri $MCP_URL -Method POST -Headers $headers -Body $callBody -UseBasicParsing

# 4. Parse and pretty-print
$line = ($result.Content -split "`n" | Where-Object { $_ -like "data:*" }) -replace "^data: ", ""
$json = $line | ConvertFrom-Json
$stockData = $json.result.content[0].text | ConvertFrom-Json
$stockData | Format-List