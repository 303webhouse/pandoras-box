@echo off
REM Wrapper around package-skill.ps1 so it can be run from cmd or a double-click.
REM Bypasses ExecutionPolicy so unsigned scripts run without prompting.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0package-skill.ps1" %*
