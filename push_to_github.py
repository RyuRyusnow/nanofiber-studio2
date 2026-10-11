import os
import sys
import subprocess
import shutil
import webbrowser

# Windows コンソールでの文字エンコーディング設定
if sys.platform == "win32":
    try:
        # UTF-8 出力を設定（非対応文字は置換）
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def print_banner():
    print("=" * 66)
    print("  Nanofiber Studio - GitHub アップロードツール (Streamlit Cloud準備)")
    print("=" * 66)
    print()

def main():
    print_banner()

    # 1. カレントディレクトリを作業フォルダに設定
    app_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(app_dir)

    # 2. Git のインストール確認
    git_bin = shutil.which("git")
    if not git_bin:
        print("[エラー] Git がシステムに見つかりません。")
        print("   https://git-scm.com/downloads から Git をインストールしてください。")
        input("\nEnter キーを押して終了します...")
        return 1

    # 3. Git リポジトリ状態の確認とコミット
    if not os.path.exists(os.path.join(app_dir, ".git")):
        print("[準備] Git リポジトリを初期化しています...")
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "branch", "-M", "main"], check=True)

    # 未コミットの変更があれば自動でコミット
    status_proc = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if status_proc.stdout.strip():
        print("[更新] 最新の変更をローカルコミットしています...")
        subprocess.run(["git", "add", "."], check=True)
        config_name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        if not config_name:
            subprocess.run(["git", "config", "user.name", "ryugo"], check=True)
            subprocess.run(["git", "config", "user.email", "ryugo@users.noreply.github.com"], check=True)
        subprocess.run(["git", "commit", "-m", "Update project for Streamlit Cloud"], check=True)

    print("[OK] ローカルプロジェクトの準備が完了しています。\n")

    # 4. ステップ 1: GitHub リポジトリ作成の案内
    print("------------------------------------------------------------------")
    print("【ステップ 1】GitHub 上で新しいリポジトリを作成してください")
    print("------------------------------------------------------------------")
    print("・リポジトリ名 (例): nanofiber-studio")
    print("・公開設定: Private (非公開・推奨) または Public")
    print("・注意: 「Add a README file」等のチェックは外したままで作成してください")
    print()

    open_browser = input(">> ブラウザで GitHub 新規作成ページを開きますか？ [Y/n]: ").strip().lower()
    if open_browser in ("", "y", "yes"):
        print("[Web] ブラウザを開いています: https://github.com/new")
        webbrowser.open("https://github.com/new")
        print()

    # 5. ステップ 2: リポジトリ URL の入力
    print("------------------------------------------------------------------")
    print("【ステップ 2】作成した GitHub リポジトリの URL を入力してください")
    print("------------------------------------------------------------------")
    print("（例: https://github.com/ユーザー名/nanofiber-studio.git）")
    print("※ コピーしたURLは右クリックまたは Ctrl+V で貼り付けられます。")
    print()

    repo_url = input("GitHub URL: ").strip().strip('"').strip("'")
    if not repo_url:
        print("\n[注意] URLが入力されませんでした。処理を中断します。")
        input("\nEnter キーを押して終了します...")
        return 0

    # 簡易URLバリデーション
    if not (repo_url.startswith("https://") or repo_url.startswith("git@")):
        print(f"\n[注意] 入力されたURLの形式が正しくない可能性があります: {repo_url}")
        proceed = input("このまま続行しますか？ [y/N]: ").strip().lower()
        if proceed not in ("y", "yes"):
            print("\n処理を中断しました。")
            input("\nEnter キーを押して終了します...")
            return 0

    print()
    print("------------------------------------------------------------------")
    print("【ステップ 3】GitHub へファイルを送信中...")
    print("------------------------------------------------------------------")

    # リモート origin の更新
    subprocess.run(["git", "remote", "remove", "origin"], capture_output=True)
    add_remote_res = subprocess.run(["git", "remote", "add", "origin", repo_url], capture_output=True, text=True)
    if add_remote_res.returncode != 0:
        print(f"[エラー] リモートの追加に失敗しました: {add_remote_res.stderr}")
        input("\nEnter キーを押して終了します...")
        return 1

    subprocess.run(["git", "branch", "-M", "main"], check=True)

    # git push の実行
    print("[送信] git push -u origin main を実行しています...\n")
    push_res = subprocess.run(["git", "push", "-u", "origin", "main"])

    print()
    if push_res.returncode == 0:
        print("==================================================================")
        print("  【大成功】 GitHub へのプロジェクト送信が完了しました！")
        print("==================================================================")
        print()
        print("続けて以下の手順で Streamlit Cloud にデプロイしてください：")
        print("1. https://share.streamlit.io を開く (GitHubアカウントでログイン)")
        print("2. 画面右上の「New app」ボタンを押す")
        print("3. Repository: 先ほど作成したリポジトリを選択")
        print("4. Main file path: app.py を確認")
        print("5. 「Deploy!」をクリック")
        print("   -> 数分で世界中（iPhoneの4G/5G・外出先Wi-Fi）からアクセスできるURLが発行されます！")
        print()

        open_streamlit = input(">> 今すぐブラウザで Streamlit Cloud を開きますか？ [Y/n]: ").strip().lower()
        if open_streamlit in ("", "y", "yes"):
            print("[Web] ブラウザを開いています: https://share.streamlit.io")
            webbrowser.open("https://share.streamlit.io")
    else:
        print("==================================================================")
        print("  【送信失敗】 GitHub へのプッシュ中にエラーが発生しました")
        print("==================================================================")
        print()
        print("【よくある原因と対処法】")
        print("1. GitHub の認証（ログイン）が必要な場合:")
        print("   ブラウザ認証ポップアップが表示された場合は、ログインを許可してください。")
        print("2. リポジトリURLの誤字:")
        print("   GitHub 上でリポジトリが実際に作成されているか確認してください。")
        print("3. リモートに既にコミットが存在する場合 (READMEなど):")
        print("   空のリポジトリを作成して再度このスクリプトを実行してください。")

    print()
    input("何かキーを押すとこの画面を閉じます...")
    return push_res.returncode

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n中断されました。")
        sys.exit(1)
    except Exception as e:
        print(f"\n予期しないエラーが発生しました: {e}")
        input("\nEnter キーを押して終了します...")
        sys.exit(1)
