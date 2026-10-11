@echo off
setlocal EnableDelayedExpansion
title Nanofiber Studio - Windows Auto-Start Setup

echo ========================================================
echo   Nanofiber Studio - PC起動時の自動起動セットアップ
echo   (PC起動時にバックグラウンド待機し、iPhoneから即座に利用可能にします)
echo ========================================================
echo.

cd /d "%~dp0"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET_VBS=%STARTUP_DIR%\NanofiberStudio_Launcher.vbs"

echo [1/3] Windowsスタートアップフォルダを確認中...
if not exist "%STARTUP_DIR%" (
    echo [ERROR] スタートアップフォルダが見つかりません: %STARTUP_DIR%
    pause
    exit /b 1
)

echo [2/3] 自動起動スクリプトをスタートアップに登録中...
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%~dp0"
echo WshShell.Run "cmd /c py launcher.py", 0, False
) > "%TARGET_VBS%"

rem IPアドレスを自動検出
for /f "tokens=*" %%i in ('py -c "import launcher; print(launcher.get_local_ip())" 2^>nul') do set "LOCAL_IP=%%i"
if "%LOCAL_IP%"=="" set "LOCAL_IP=192.168.1.13"

echo.
echo [3/3] リモートランチャーを今すぐバックグラウンド起動中...
wscript.exe "%TARGET_VBS%"

echo.
echo ========================================================
echo   [完了] 自動起動の登録が完了しました！
echo.
echo   ・PC起動時（ログイン時）に自動的にバックグラウンド待機します
echo   ・黒い画面は出ず、常時静かに待機します
echo.
echo   【iPhone / スマホからのアクセス先】
echo   ・Nanofiber Studio アプリ本体:   http://%LOCAL_IP%:8501
echo   ・リモート起動・管理ポータル:     http://%LOCAL_IP%:8500
echo.
echo   ※ iPhoneのSafariで http://%LOCAL_IP%:8500 を開き、
echo      「ホーム画面に追加」しておくと、いつでも1タップで
echo      サーバーを起動・確認・停止できます。
echo ========================================================
echo.
pause
