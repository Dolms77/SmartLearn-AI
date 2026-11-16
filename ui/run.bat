@echo off
rem Double-click to start the SmartStudy UI (bypasses PowerShell execution policy).
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
endlocal
