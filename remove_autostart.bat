@echo off
setlocal
title Nanofiber Studio - Windows Auto-Start Removal

echo ========================================================
echo   Nanofiber Studio - 自動起動の解除
echo ========================================================
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET_VBS=%STARTUP_DIR%\NanofiberStudio_Launcher.vbs"

if exist "%TARGET_VBS%" (
    del /f /q "%TARGET_VBS%"
    echo [OK] スタートアップ登録を解除しました。
    echo      次回PC起動時からは自動起動されません。
) else (
    echo [INFO] 自動起動は登録されていませんでした。
)
echo.
pause
