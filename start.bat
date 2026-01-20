@echo off
echo.
echo ========================================
echo   Starting Pandora's Box
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ and try again
    pause
    exit /b 1
)

echo [1/3] Starting backend server...
cd /d "%~dp0backend"
start "Pandora's Box Backend" cmd /k "python main.py"
timeout /t 3 /nobreak >nul

echo [2/3] Starting frontend server...
cd /d "%~dp0frontend"
start "Pandora's Box Frontend" cmd /k "python -m http.server 3000"
timeout /t 2 /nobreak >nul

echo [3/3] Opening dashboard...
timeout /t 3 /nobreak >nul
start http://localhost:3000

echo.
echo ========================================
echo   Pandora's Box is running!
echo ========================================
echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo.
echo Do you want to populate test signals? (Y/N)
set /p populate="Enter choice: "
if /i "%populate%"=="Y" (
    echo.
    echo Populating test data...
    cd /d "%~dp0backend"
    python test_signals.py
)
echo.
echo Press any key to stop all services...
pause >nul

echo.
echo Stopping services...
taskkill /FI "WindowTitle eq Pandora's Box Backend*" /F >nul 2>&1
taskkill /FI "WindowTitle eq Pandora's Box Frontend*" /F >nul 2>&1
echo.
echo Services stopped. Goodbye!
timeout /t 2 /nobreak >nul
