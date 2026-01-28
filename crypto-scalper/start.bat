@echo off
echo ========================================
echo    Crypto Scalper - Starting...
echo    BTC Trading Signals for Breakout
echo ========================================
echo.

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Install dependencies if needed
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt -q

echo.
echo Starting Crypto Scalper backend on port 8001...
echo Frontend will be available at: http://localhost:8001/app
echo.

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

pause
