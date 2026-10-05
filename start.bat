@echo off
title IntentGuard Launcher
cd /d "%~dp0"

echo ==============================================================================
echo                      STARTING INTENTGUARD SERVICES
echo ==============================================================================
echo.

:: 1. Check for .env file
if not exist ".env" (
    echo [INFO] Creating .env from .env.example...
    copy .env.example .env >nul
)

:: 2. Check for virtual environment activation script
set "VENV_ACTIVATE="
if exist ".venv\Scripts\activate.bat" (
    set "VENV_ACTIVATE=call .venv\Scripts\activate.bat && "
    echo [INFO] Detected virtual environment: .venv
)

:: 3. Start Mock Payment Service Sandbox (Port 8001)
echo [1/3] Starting Mock Payment Service Sandbox on port 8001...
start "IntentGuard - Mock Payment Service (Port 8001)" cmd /k "cd /d "%~dp0" && %VENV_ACTIVATE%python -m uvicorn mock-payment-service.app.main:app --host 127.0.0.1 --port 8001 --reload"

timeout /t 2 /nobreak >nul

:: 4. Start IntentGuard Safety Gateway Backend (Port 8000)
echo [2/3] Starting IntentGuard Gateway Backend on port 8000...
start "IntentGuard - Gateway Backend (Port 8000)" cmd /k "cd /d "%~dp0" && %VENV_ACTIVATE%python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 2 /nobreak >nul

:: 5. Start React Frontend Dashboard (Port 3000)
echo [3/3] Starting React Frontend Dashboard on port 3000...
start "IntentGuard - Frontend Dashboard (Port 3000)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

timeout /t 3 /nobreak >nul

:: 6. Launch browser to dashboard
echo.
echo ==============================================================================
echo  All 3 services launched successfully!
echo   - Frontend Dashboard:      http://localhost:3000
echo   - Gateway API Docs:        http://127.0.0.1:8000/docs
echo   - Mock Payment Simulator:  http://127.0.0.1:8001/docs
echo ==============================================================================
echo.
echo Opening browser at http://localhost:3000 ...
start http://localhost:3000

echo.
echo To stop services, close the 3 command prompt windows or run stop.bat.
pause
