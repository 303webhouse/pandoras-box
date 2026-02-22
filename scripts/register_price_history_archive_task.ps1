param(
    [string]$TaskName = "TradingHub-PriceHistoryArchive",
    [string]$StartTime = "02:15"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runnerScript = Join-Path $repoRoot "scripts\run_price_history_archive.ps1"

if (-not (Test-Path $runnerScript)) {
    throw "Runner script not found: $runnerScript"
}

$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runnerScript`""

# Create/update the scheduled task.
schtasks /Create `
    /TN $TaskName `
    /SC DAILY `
    /ST $StartTime `
    /TR $action `
    /F | Out-Null

Write-Output "Scheduled task created/updated: $TaskName"
schtasks /Query /TN $TaskName /V /FO LIST
