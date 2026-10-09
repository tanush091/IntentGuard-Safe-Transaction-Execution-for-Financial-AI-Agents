@echo off
setlocal EnableExtensions
title IntentGuard Launcher
:: Run from the repository root (this script lives in scripts\).
cd /d "%~dp0.."
set "ROOT=%CD%"

echo ==============================================================================
echo                      STARTING INTENTGUARD SERVICES
echo ==============================================================================
echo.

:: ---------------------------------------------------------------- 1. config
if not exist ".env" (
    echo [INFO] Creating .env from .env.example...
    copy .env.example .env >nul
)

:: The old prototype's database (intentguard.db) has an incompatible schema.
findstr /B /C:"DATABASE_URL=sqlite:///./intentguard.db" .env >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Pointing DATABASE_URL in .env at intentguard_gateway.db ^(old file left untouched^)
    powershell -NoProfile -Command "$p=(Resolve-Path '.env').Path; $c=[IO.File]::ReadAllLines($p) -replace '^DATABASE_URL=sqlite:///\./intentguard\.db$','DATABASE_URL=sqlite:///./intentguard_gateway.db'; [IO.File]::WriteAllLines($p,$c)"
)

:: ------------------------------------------------------------- 2. python env
set "VENV_ACTIVATE="
if exist ".venv\Scripts\activate.bat" (
    call "%ROOT%\.venv\Scripts\activate.bat"
    set "VENV_ACTIVATE=call "%ROOT%\.venv\Scripts\activate.bat" && "
    echo [INFO] Using virtual environment .venv
) else if exist "backend\.venv\Scripts\activate.bat" (
    call "%ROOT%\backend\.venv\Scripts\activate.bat"
    set "VENV_ACTIVATE=call "%ROOT%\backend\.venv\Scripts\activate.bat" && "
    echo [INFO] Using virtual environment backend\.venv
) else if exist "venv\Scripts\activate.bat" (
    call "%ROOT%\venv\Scripts\activate.bat"
    set "VENV_ACTIVATE=call "%ROOT%\venv\Scripts\activate.bat" && "
    echo [INFO] Using virtual environment venv
)

python -c "import fastapi, uvicorn, sqlalchemy, httpx, numpy, pydantic_settings, jwt, argon2, dotenv" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing Python dependencies...
    python -m pip install -r backend\requirements.txt || goto :fail
)

:: Fill in JWT_SECRET and WEBHOOK_SECRET in .env (generated locally, never committed).
python scripts\init_env.py || goto :fail

:: Install when node_modules is missing or no longer matches package.json (e.g. after a pull).
pushd frontend
set "_npm_ok=1"
if not exist "node_modules" set "_npm_ok="
if defined _npm_ok (
    call npm ls --depth=0 >nul 2>&1 || set "_npm_ok="
)
if not defined _npm_ok (
    echo [INFO] Installing dashboard dependencies...
    call npm install || (popd & goto :fail)
    rem Vite's pre-bundled dependency cache can outlive an upgrade and break the dev server.
    if exist "node_modules\.vite" rmdir /s /q "node_modules\.vite"
)
popd

:: ------------------------------- 3. stop a previous IntentGuard run, check ports
call :stop_all quiet
:: A database from an earlier schema is moved aside as a backup (with the simulator state), not deleted.
python scripts\check_db.py || goto :fail
call :require_free 8001 || goto :fail
call :require_free 8000 || goto :fail

:: The dashboard uses 3000, or the next free port if another app already has it.
set "DASH_PORT="
for /f %%p in ('powershell -NoProfile -Command "foreach($p in 3000..3020){ if(-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)){ $p; break } }"') do set "DASH_PORT=%%p"
if not defined DASH_PORT (
    echo [ERROR] No free port between 3000 and 3020 for the dashboard.
    goto :fail
)
if not "%DASH_PORT%"=="3000" echo [INFO] Port 3000 is used by another program; the dashboard will use port %DASH_PORT%.

:: ---------------------------------------------------------------- 4. launch
echo [1/3] Starting mock payment provider on port 8001...
start "IntentGuard - Provider (8001)" cmd /k "cd /d "%ROOT%" && %VENV_ACTIVATE%cd backend && python -m uvicorn provider_api.main:app --host 127.0.0.1 --port 8001"
call :wait_for http://127.0.0.1:8001/health "payment provider" || goto :fail

echo [2/3] Starting IntentGuard gateway on port 8000...
start "IntentGuard - Gateway (8000)" cmd /k "cd /d "%ROOT%" && %VENV_ACTIVATE%cd backend && python -m uvicorn gateway_api.main:app --host 127.0.0.1 --port 8000"
call :wait_for http://127.0.0.1:8000/health "gateway" || goto :fail

echo [3/3] Starting dashboard on port %DASH_PORT%...
start "IntentGuard - Dashboard (%DASH_PORT%)" cmd /k "cd /d "%ROOT%\frontend" && npm run dev -- --port %DASH_PORT% --strictPort"
call :wait_for http://localhost:%DASH_PORT% "dashboard" || goto :fail

echo.
echo ==============================================================================
echo  All services are running:
echo    Dashboard ............ http://localhost:%DASH_PORT%
echo    Gateway API docs ..... http://127.0.0.1:8000/docs
echo    Payment provider ..... http://127.0.0.1:8001/docs
echo ==============================================================================
start "" http://localhost:%DASH_PORT%

echo.
echo  Press any key in THIS window to stop all IntentGuard services.
pause >nul
call :stop_all
echo All IntentGuard services stopped.
ping -n 3 127.0.0.1 >nul
exit /b 0

:fail
echo.
echo [ERROR] Startup failed. See the messages above and the service windows.
echo Press any key to stop whatever was started.
pause >nul
call :stop_all
exit /b 1

:: ============================================================== subroutines

:wait_for
:: %1 = URL, %2 = name. Waits up to 60 seconds for an HTTP response.
set /a _tries=0
:wait_loop
curl -s -o nul "%~1" >nul 2>&1
if not errorlevel 1 (
    echo       %~2 is up.
    exit /b 0
)
set /a _tries+=1
if %_tries% geq 60 (
    echo [ERROR] %~2 did not respond at %~1 within 60 seconds.
    exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto :wait_loop

:require_free
:: Fails (without killing anything) if another program is listening on port %1.
set "_owner="
for /f "delims=" %%o in ('powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %1 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($c){ $p=Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue; '{0} (PID {1})' -f $p.ProcessName,$c.OwningProcess }"') do set "_owner=%%o"
if defined _owner (
    echo [ERROR] Port %1 is already used by %_owner%. Close that program and run start.bat again.
    exit /b 1
)
exit /b 0

:stop_all
:: Stops only IntentGuard processes: the windows start.bat opened (with their child
:: processes), plus any IntentGuard uvicorn/vite process started some other way.
:: Other programs are never touched, even if they use the same ports.
if /i not "%~1"=="quiet" echo Stopping IntentGuard services...
taskkill /F /T /FI "WINDOWTITLE eq IntentGuard - *" >nul 2>&1
powershell -NoProfile -Command "$root=(Resolve-Path '.').Path; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'uvicorn\s+(gateway_api|provider_api)\.main:app' -or $_.CommandLine -like ('*' + $root + '\frontend\*vite*')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
exit /b 0
