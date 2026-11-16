@echo off
chcp 65001 >nul
title SmartStudy - UI
echo.
echo ============================================
echo   SmartStudy - Step 3/3 : start the UI
echo   Open http://localhost:8501 after it boots
echo ============================================
echo.
call "%~dp0ui\run.bat"
pause
