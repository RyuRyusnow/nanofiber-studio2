@echo off
setlocal
title Nanofiber Studio - Windows Auto-Start Removal

echo ========================================================
echo   Nanofiber Studio - Auto-Start Removal
echo ========================================================
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET_VBS=%STARTUP_DIR%\NanofiberStudio_Launcher.vbs"

if exist "%TARGET_VBS%" (
    del /f /q "%TARGET_VBS%"
    echo [OK] Auto-start registration removed successfully.
) else (
    echo [INFO] Auto-start was not registered.
)
echo.
pause
