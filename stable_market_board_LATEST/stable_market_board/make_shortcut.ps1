# Creates a "Stable Market Board" shortcut on your desktop.
# Run from PowerShell: .\make_shortcut.ps1
# Or right-click the file and "Run with PowerShell"

$projectPath = $PSScriptRoot
$batPath = Join-Path $projectPath "run_dashboard.bat"

if (-not (Test-Path $batPath)) {
    Write-Host "Error: run_dashboard.bat not found in this folder." -ForegroundColor Red
    Write-Host "Make sure you're running this from the project root." -ForegroundColor Red
    exit 1
}

# Find the user's Desktop (handles OneDrive-redirected desktops)
$desktop = [Environment]::GetFolderPath("Desktop")
if (-not (Test-Path $desktop)) {
    $desktop = "$env:USERPROFILE\Desktop"
}

$shortcutPath = Join-Path $desktop "Stable Market Board.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $batPath
$shortcut.WorkingDirectory = $projectPath
$shortcut.IconLocation = "C:\Windows\System32\imageres.dll,76"
$shortcut.Description = "Stable Market Board - daily run"
$shortcut.Save()

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Shortcut created at: $shortcutPath"
Write-Host ""
Write-Host "Double-click 'Stable Market Board' on your desktop to launch."
Write-Host ""
