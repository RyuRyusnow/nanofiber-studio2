@echo off
setlocal
title Nanofiber Studio - Initial Setup

echo ========================================================
echo   Nanofiber Studio - Setup for New PC
echo ========================================================
echo.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto :INSTALL
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :INSTALL
)

echo [ERROR] Python not found.
echo Please install Python from https://www.python.org/
echo (Make sure to check "Add Python to PATH" during installation)
echo.
pause
exit /b 1

:INSTALL
echo [1/3] Python detected: %PY_CMD%
echo [2/3] Installing required packages (streamlit, pandas, plotly, etc.)...
"%PY_CMD%" -m pip install -r requirements.txt

echo [3/4] Creating Desktop shortcuts...
"%PY_CMD%" create_shortcut.py

echo [4/4] Syncing fabrication records with Google Drive...
"%PY_CMD%" -c "import sync_manager; res = sync_manager.sync_with_cloud(); print('   [Cloud Sync] Linked:', res.get('total_records', 0), 'records')" 2>nul

echo.
echo ========================================================
echo   Setup Complete! Starting Nanofiber Studio...
echo ========================================================
echo.
call run_app.bat
