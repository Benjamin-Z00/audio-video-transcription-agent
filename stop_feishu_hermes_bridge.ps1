$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "feishu-hermes-bridge.pid"

if (-not (Test-Path $PidFile)) {
  "not running"
  exit 0
}

$pidText = Get-Content $PidFile | Select-Object -First 1
$proc = $null
if ($pidText) {
  $proc = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
}

if ($proc) {
  Stop-Process -Id $proc.Id
  "stopped pid=$($proc.Id)"
} else {
  "pid not active"
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
