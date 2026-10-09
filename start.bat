@echo off
setlocal EnableExtensions
title IntentGuard Launcher
call "%~dp0scripts\start.bat" %*
exit /b %ERRORLEVEL%
