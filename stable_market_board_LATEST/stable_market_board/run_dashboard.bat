@echo off
title Stable Market Board
cd /d "%~dp0"
echo.
echo ============================================================
echo  STABLE MARKET BOARD - Daily Run
echo  %DATE% %TIME%
echo ============================================================
echo.
echo [1/3] Pulling latest market data from Polygon...
python -m stable.ingest
if errorlevel 1 goto error
echo.
echo [2/3] Computing metrics...
python -m stable.metrics
if errorlevel 1 goto error
echo.
echo [3/3] Starting dashboard server...
echo.
echo Opening browser to http://localhost:8000 in 3 seconds...
start "" /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"
python -m stable.server
goto end
:error
echo.
echo ============================================================
echo  ERROR - something went wrong above.
echo  Read the message, then press any key to close this window.
echo  If you need help, run: python install_check.py
echo ============================================================
pause >nul
:end
