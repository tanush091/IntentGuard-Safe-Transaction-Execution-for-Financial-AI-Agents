@echo off
setlocal EnableExtensions
title IntentGuard Stopper
call "%~dp0scripts\stop.bat" %*
exit /b %ERRORLEVEL%
