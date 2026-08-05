$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$StdoutLog = Join-Path $Root "feishu-hermes-bridge.wrapper.out.log"
$StderrLog = Join-Path $Root "feishu-hermes-bridge.wrapper.err.log"
$PidFile = Join-Path $Root "feishu-hermes-bridge.pid"
$Script = Join-Path $Root "feishu_hermes_bridge.py"

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
  $python = (Get-Command py -ErrorAction SilentlyContinue).Source
}
if (-not $python) {
  throw "Python not found"
}

$existing = $null
if (Test-Path $PidFile) {
  $oldPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($oldPid) {
    $existing = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
  }
}
if ($existing) {
  Write-Output "already running pid=$($existing.Id)"
  exit 0
}

$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:HERMES_HOME = Join-Path $Root ".hermes-bind"

$UserEnvNames = @("HERMES_STT_API_KEY", "OPENROUTER_API_KEY", "HERMES_STT_PROVIDER", "HERMES_STT_MODEL")
foreach ($name in $UserEnvNames) {
  $value = [Environment]::GetEnvironmentVariable($name, "User")
  if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

$proc = Start-Process `
  -FilePath $python `
  -ArgumentList @($Script) `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $StdoutLog `
  -RedirectStandardError $StderrLog `
  -PassThru

$proc.Id | Set-Content -Encoding ASCII $PidFile
Write-Output "started pid=$($proc.Id)"


