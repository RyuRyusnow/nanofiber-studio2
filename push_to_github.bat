@echo off
chcp 65001 > nul
echo ========================================================
echo  GitHub へプロジェクトをアップロード (Streamlit Cloud準備)
echo ========================================================
echo.
echo 1. ブラウザで GitHub (https://github.com/new) を開きます。
echo 2. Repository name に任意の名前 (例: nanofiber-studio) を入力して
echo    「Create repository」をクリックします。
echo 3. 画面に表示されるURL (https://github.com/.../nanofiber-studio.git) を
echo    以下に貼り付けて Enter を押してください。
echo.
set /p REPO_URL="GitHubリポジトリのURL: "

if "%REPO_URL%"=="" (
    echo.
    echo URLが入力されませんでした。終了します。
    pause
    exit /b
)

cd /d "%~dp0"
git remote remove origin >nul 2>&1
git remote add origin %REPO_URL%
git branch -M main
echo.
echo GitHubに送信中...
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  [成功] GitHubへのアップロードが完了しました！
    echo ========================================================
    echo.
    echo 続けて以下の手順で Streamlit Cloud にデプロイしてください：
    echo 1. https://share.streamlit.io を開く (GitHubでログイン)
    echo 2. 「New app」ボタンを押す
    echo 3. リポジトリで今作成したものを選択し「Deploy!」を押す
    echo 4. 数分で世界中どこからでもアクセスできる固定URLが発行されます！
    echo.
) else (
    echo.
    echo [エラー] 送信に失敗しました。URLやGitHubのログイン設定を確認してください。
)
pause
