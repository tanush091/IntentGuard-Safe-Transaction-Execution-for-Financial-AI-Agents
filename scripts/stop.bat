@echo off
setlocal EnableExtensions
title IntentGuard Stopper
:: Run from the repository root (this script lives in scripts\).
cd /d "%~dp0.."

echo Stopping IntentGuard services...

:: Only IntentGuard processes are stopped: the windows opened by start.bat (with their
:: child processes) and any IntentGuard uvicorn/vite process started some other way.
:: Other programs using ports 3000/8000/8001 are left alone.
taskkill /F /T /FI "WINDOWTITLE eq IntentGuard - *" >nul 2>&1
powershell -NoProfile -Command "$root=(Resolve-Path '.').Path; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'uvicorn\s+(gateway_api|provider_api)\.main:app' -or $_.CommandLine -like ('*' + $root + '\frontend\*vite*')) } | ForEach-Object { Write-Host ('  stopping PID {0}' -f $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo All IntentGuard services stopped.
ping -n 3 127.0.0.1 >nul
