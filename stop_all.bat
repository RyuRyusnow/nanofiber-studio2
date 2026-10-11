@echo off
setlocal
title Nanofiber Studio - Stop All Servers

echo ========================================================
echo   Nanofiber Studio - サーバー＆ランチャーの停止
echo ========================================================
echo.

cd /d "%~dp0"

echo サーバーおよびランチャープロセスを停止しています...
py -c "import launcher; launcher.stop_streamlit_process()" 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8500 :8501" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [OK] すべてのサーバープロセスを停止しました。
echo.
pause
