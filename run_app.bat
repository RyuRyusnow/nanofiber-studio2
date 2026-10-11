@echo off
setlocal
title Nanofiber Studio - Server

echo ========================================================
echo   Nanofiber Studio - Optical Nanofiber Manager
echo ========================================================
echo.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto :START_SERVER
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :START_SERVER
)

echo [ERROR] Python not found.
pause
exit /b 1

:START_SERVER
echo [1/3] Detecting network IP address...
for /f "tokens=*" %%i in ('"%PY_CMD%" -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set LOCAL_IP=%%i
if "%LOCAL_IP%"=="" set LOCAL_IP=localhost

echo.
echo ========================================================
echo   [PC Browser URL]     http://localhost:8501
echo   [iPhone / Mobile]    http://%LOCAL_IP%:8501
echo ========================================================
echo.
echo [2/3] Opening browser at http://localhost:8501 ...
start "" http://localhost:8501
echo [3/3] Starting server on 0.0.0.0:8501 (accessible from iPhone)...
"%PY_CMD%" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Streamlit failed or stopped unexpectedly (code: %errorlevel%).
    pause
)
