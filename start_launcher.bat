@echo off
setlocal
title Nanofiber Studio - Remote Launcher for iPhone

echo ========================================================
echo   Nanofiber Studio - Remote Launcher & iPhone Portal
echo ========================================================
echo.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto :RUN
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :RUN
)

echo [ERROR] Python not found.
pause
exit /b 1

:RUN
"%PY_CMD%" launcher.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Launcher stopped with exit code %errorlevel%.
    pause
)
