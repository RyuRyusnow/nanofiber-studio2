@echo off
setlocal
title Nanofiber Studio - Stop All Servers

echo ========================================================
echo   Nanofiber Studio - Stopping Servers
echo ========================================================
echo.

cd /d "%~dp0"

echo Stopping server and launcher processes...
py -c "import launcher; launcher.stop_streamlit_process()" 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8500 :8501" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [OK] All servers have been stopped.
echo.
pause
