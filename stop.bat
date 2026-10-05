@echo off
title IntentGuard Stopper
cd /d "%~dp0"

echo ==============================================================================
echo                      STOPPING INTENTGUARD SERVICES
echo ==============================================================================
echo.

echo Stopping services running on ports 8000, 8001, and 3000...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a on port 8000...
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a on port 8001...
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    echo Terminating PID %%a on port 3000...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo All IntentGuard services stopped.
pause
