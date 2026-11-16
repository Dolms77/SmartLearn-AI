@echo off
chcp 65001 >nul
title SmartStudy - Run pipeline
echo.
echo ============================================
echo   SmartStudy - Step 2/3 : run pipeline 01..06
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_all.ps1" %*
echo.
if errorlevel 1 (
  echo [FAILED] see messages above.
  echo Troubleshooting: docs\reproduction-handbook (see folder docs)
) else (
  echo [DONE] artifacts verified. Next: double-click "3_start_ui.bat"
)
echo.
pause
