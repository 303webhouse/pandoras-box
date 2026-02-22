param(
    [int]$OlderThanDays = 0,
    [int]$BatchSize = 0,
    [switch]$NoPurge,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Resolve-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    throw "Python executable not found in PATH."
}

function Read-IntEnv([string]$Name, [int]$Default, [int]$Min = 1) {
    $raw = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $Default
    }
    $parsed = 0
    if ([int]::TryParse($raw, [ref]$parsed)) {
        if ($parsed -lt $Min) {
            return $Min
        }
        return $parsed
    }
    return $Default
}

function Read-BoolEnv([string]$Name, [bool]$Default) {
    $raw = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $Default
    }
    $normalized = $raw.Trim().ToLowerInvariant()
    if ($normalized -in @("1", "true", "yes", "on")) {
        return $true
    }
    if ($normalized -in @("0", "false", "no", "off")) {
        return $false
    }
    return $Default
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$archiveDir = [Environment]::GetEnvironmentVariable("PRICE_HISTORY_ARCHIVE_DIR")
if ([string]::IsNullOrWhiteSpace($archiveDir)) {
    $archiveDir = "data/archives/price_history"
}

$effectiveOlderThanDays = $OlderThanDays
if ($effectiveOlderThanDays -le 0) {
    $effectiveOlderThanDays = Read-IntEnv -Name "PRICE_HISTORY_ARCHIVE_OLDER_THAN_DAYS" -Default 2 -Min 1
}

$effectiveBatchSize = $BatchSize
if ($effectiveBatchSize -le 0) {
    $effectiveBatchSize = Read-IntEnv -Name "PRICE_HISTORY_ARCHIVE_BATCH_SIZE" -Default 25000 -Min 100
}

$purgeEnabled = Read-BoolEnv -Name "PRICE_HISTORY_ARCHIVE_PURGE" -Default $true
if ($NoPurge) {
    $purgeEnabled = $false
}

$logDir = Join-Path $archiveDir "logs"
New-Item -Path $logDir -ItemType Directory -Force | Out-Null

$lockPath = Join-Path $logDir "archive.lock"
$now = Get-Date
$todayLogFile = Join-Path $logDir ("archive_{0}.log" -f $now.ToString("yyyy-MM-dd"))

if (Test-Path $lockPath) {
    $lockAgeHours = ($now - (Get-Item $lockPath).LastWriteTime).TotalHours
    if ($lockAgeHours -lt 12) {
        $msg = "{0} archive skipped: active lock file exists ({1})" -f $now.ToString("s"), $lockPath
        $msg | Tee-Object -FilePath $todayLogFile -Append | Out-Host
        exit 0
    }
    Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
}

$pythonCmd = Resolve-PythonCommand
$cmdArgs = @(
    "-m", "backend.jobs.archive_price_history",
    "--older-than-days", $effectiveOlderThanDays.ToString(),
    "--batch-size", $effectiveBatchSize.ToString()
)

if ($purgeEnabled) {
    $cmdArgs += "--purge"
}
if ($DryRun) {
    $cmdArgs += "--dry-run"
}

if (-not [string]::IsNullOrWhiteSpace($archiveDir)) {
    $cmdArgs += @("--archive-dir", $archiveDir)
}

$startLine = "{0} archive start | purge={1} dry_run={2} older_than_days={3} batch_size={4}" -f `
    (Get-Date).ToString("s"), $purgeEnabled, $DryRun.IsPresent, $effectiveOlderThanDays, $effectiveBatchSize
$startLine | Tee-Object -FilePath $todayLogFile -Append | Out-Host

try {
    Set-Content -Path $lockPath -Value ("started_at={0}" -f (Get-Date).ToString("o")) -Encoding UTF8
    & $pythonCmd @cmdArgs 2>&1 | Tee-Object -FilePath $todayLogFile -Append | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "archive job exited with code $LASTEXITCODE"
    }
    $endLine = "{0} archive success" -f (Get-Date).ToString("s")
    $endLine | Tee-Object -FilePath $todayLogFile -Append | Out-Host
}
catch {
    $errorLine = "{0} archive failure: {1}" -f (Get-Date).ToString("s"), $_
    $errorLine | Tee-Object -FilePath $todayLogFile -Append | Out-Host
    throw
}
finally {
    Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
}

