@echo off
setlocal
title Nanofiber Studio - GitHub Upload
set "APP_DIR=C:\Users\ryugo.DESKTOP-KGQTT11\.gemini\antigravity\scratch\nanofiber_manager"
if not exist "%APP_DIR%\push_to_github.py" (
    set "APP_DIR=%~dp0"
)
cd /d "%APP_DIR%"
py push_to_github.py
if %errorlevel% neq 0 (
    echo.
    echo [Process exited with code %errorlevel%]
    pause
)
