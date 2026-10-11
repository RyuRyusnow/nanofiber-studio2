@echo off
setlocal
title Nanofiber Studio - Firewall Setup

echo ========================================================
echo   Windows Firewall Rule Setup for Nanofiber Studio
echo   (Port 8501 TCP - Allow connection from iPhone / Mobile)
echo ========================================================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Administrator rights are required.
    echo Please right-click this file and select "Run as administrator" (管理者として実行).
    echo.
    pause
    exit /b 1
)

netsh advfirewall firewall delete rule name="Nanofiber Studio (Streamlit 8501)" >nul 2>&1
netsh advfirewall firewall delete rule name="Nanofiber Studio (Ports 8500-8501)" >nul 2>&1
netsh advfirewall firewall add rule name="Nanofiber Studio (Ports 8500-8501)" dir=in action=allow protocol=TCP localport=8500,8501
if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Firewall rule added successfully!
    echo iPhone and other devices on the same Wi-Fi can now connect to:
    echo   - Port 8501: Nanofiber Studio App
    echo   - Port 8500: Remote Launcher Portal
) else (
    echo.
    echo [ERROR] Failed to add firewall rule.
)
echo.
pause
