@echo off
chcp 65001 >nul
title SmartStudy - Install
echo.
echo ============================================
echo   SmartStudy - Step 1/3 : install deps
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" %*
echo.
if errorlevel 1 (
  echo [FAILED] see messages above.
) else (
  echo [DONE] environment is ready. Next: double-click "2_run_all.bat"
)
echo.
pause
