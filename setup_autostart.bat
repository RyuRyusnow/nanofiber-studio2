@echo off
setlocal EnableDelayedExpansion
title Nanofiber Studio - Windows Auto-Start Setup

echo ========================================================
echo   Nanofiber Studio - Windows Auto-Start Setup
echo   (Background service launcher on Windows login)
echo ========================================================
echo.

cd /d "%~dp0"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET_VBS=%STARTUP_DIR%\NanofiberStudio_Launcher.vbs"

echo [1/3] Checking Startup directory...
if not exist "%STARTUP_DIR%" (
    echo [ERROR] Startup directory not found: %STARTUP_DIR%
    pause
    exit /b 1
)

echo [2/3] Registering launcher script in Startup...
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%~dp0"
echo WshShell.Run "cmd /c py launcher.py", 0, False
) > "%TARGET_VBS%"

rem Detect local IP
for /f "tokens=*" %%i in ('py -c "import launcher; print(launcher.get_local_ip())" 2^>nul') do set "LOCAL_IP=%%i"
if "%LOCAL_IP%"=="" set "LOCAL_IP=192.168.1.13"

echo.
echo [3/3] Starting remote launcher silently in background...
wscript.exe "%TARGET_VBS%"

echo.
echo ========================================================
echo   [SUCCESS] Auto-start registered successfully!
echo.
echo   - Runs silently in background on Windows login
echo   - No terminal window popup
echo.
echo   [Mobile Access URLs]
echo   - Nanofiber Studio App:   http://%LOCAL_IP%:8501
echo   - Remote Launcher Portal: http://%LOCAL_IP%:8500
echo.
echo   Tip: Open http://%LOCAL_IP%:8500 in iPhone Safari and
echo   tap "Add to Home Screen" for 1-tap remote control.
echo ========================================================
echo.
pause
