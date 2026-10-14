@echo off
setlocal
title Nanofiber Studio - Cloud Sync
echo ========================================================
echo   Nanofiber Studio - Data Sync (Google Drive / Cloud)
echo ========================================================
echo.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto :SYNC
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :SYNC
)

echo [ERROR] Python not found.
pause
exit /b 1

:SYNC
echo [1/1] Syncing records with Google Drive / Cloud...
"%PY_CMD%" -c "import sync_manager; res = sync_manager.sync_with_cloud(); print('\n=== SYNC RESULT ==='); print('Status: Success'); print('Sync Directory:', res.get('sync_dir')); print('Pulled from Cloud:', res.get('pulled_count', 0), 'new records'); print('Updated locally:', res.get('updated_count', 0), 'records'); print('Pushed to Cloud:', res.get('pushed_count', 0), 'records'); print('Total Synchronized Records:', res.get('total_records', 0)); print('Last Synced At:', res.get('last_synced_at'))"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Synchronization encountered an issue.
) else (
    echo.
    echo [OK] All records and linked data synchronized successfully!
)
echo.
pause
