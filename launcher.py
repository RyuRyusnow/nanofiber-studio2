"""
Nanofiber Studio - Remote Server Launcher & Portal for iPhone / Mobile
Allows starting, stopping, restarting, and monitoring the Streamlit server remotely from iPhone.
Runs a lightweight HTTP server on port 8500.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

PORT_LAUNCHER = 8500
PORT_STREAMLIT = 8501
DIR_CURRENT = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(DIR_CURRENT, "app.py")

streamlit_process = None
process_lock = threading.Lock()

def get_local_ip() -> str:
    """ローカルネットワークIPアドレス（iPhoneからアクセスするIP）を取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def is_port_listening(port: int) -> bool:
    """指定ポートでTCPリスンしているか判定"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0

def check_streamlit_alive() -> bool:
    """StreamlitサーバーがHTTP 200を返すか健康診断"""
    if not is_port_listening(PORT_STREAMLIT):
        return False
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT_STREAMLIT}/",
            headers={"User-Agent": "NanofiberLauncher/1.0"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as res:
            return res.status == 200
    except Exception:
        # ポートがリスンしていれば起動中と判定
        return is_port_listening(PORT_STREAMLIT)

def start_streamlit_process():
    """Streamlitサーバーをバックグラウンドで起動"""
    global streamlit_process
    with process_lock:
        if check_streamlit_alive():
            return True, "すでに稼働中です"

        python_exe = sys.executable
        cmd = [
            python_exe,
            "-m", "streamlit", "run", "app.py",
            "--server.address", "0.0.0.0",
            "--server.port", str(PORT_STREAMLIT),
            "--server.headless", "true"
        ]

        # Windows用 CREATE_NO_WINDOW (コンソールウィンドウ非表示)
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            streamlit_process = subprocess.Popen(
                cmd,
                cwd=DIR_CURRENT,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True, "起動コマンドを実行しました"
        except Exception as e:
            return False, f"起動エラー: {str(e)}"

def stop_streamlit_process():
    """Streamlitサーバーを停止"""
    global streamlit_process
    with process_lock:
        # 1. 保持しているプロセスハンドルを終了
        if streamlit_process:
            try:
                streamlit_process.terminate()
                streamlit_process.wait(timeout=2.0)
            except Exception:
                try:
                    streamlit_process.kill()
                except Exception:
                    pass
            streamlit_process = None

        # 2. Windows netstatでポート8501を使用しているプロセスを強制終了
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(
                    f'netstat -ano | findstr :{PORT_STREAMLIT}',
                    shell=True,
                    stderr=subprocess.DEVNULL
                ).decode('latin1', errors='ignore')
                for line in out.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 5 and "LISTENING" in line:
                        pid = parts[-1]
                        subprocess.call(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        time.sleep(1)
        return True, "停止しました"

def wait_until_ready(timeout_sec: float = 8.0) -> bool:
    """Streamlitが応答可能になるまで待機"""
    start_t = time.time()
    while time.time() - start_t < timeout_sec:
        if check_streamlit_alive():
            return True
        time.sleep(0.4)
    return check_streamlit_alive()

HTML_PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Nanofiber起動">
<title>Nanofiber Studio - サーバー起動ポータル</title>
<style>
  :root {
    --bg: #0b0f17;
    --card: #141a24;
    --card-border: #232d3f;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent-blue: #38bdf8;
    --accent-green: #34d399;
    --accent-red: #f87171;
    --accent-amber: #fbbf24;
  }
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-tap-highlight-color: transparent;
  }
  body {
    background-color: var(--bg);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
    padding: 24px 16px 40px 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
  }
  .container {
    width: 100%;
    max-width: 480px;
  }
  .header {
    text-align: center;
    margin-bottom: 24px;
    padding-top: 10px;
  }
  .logo-icon {
    font-size: 46px;
    margin-bottom: 8px;
    display: inline-block;
    filter: drop-shadow(0 4px 12px rgba(56, 189, 248, 0.35));
  }
  .title {
    font-size: 1.35rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--text-primary);
    line-height: 1.25;
  }
  .subtitle {
    font-size: 0.82rem;
    color: var(--text-secondary);
    margin-top: 4px;
  }

  /* ステータスカード */
  .status-card {
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 14px;
    padding: 18px 20px;
    margin-bottom: 18px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .status-info {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .status-label {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
  }
  .status-val {
    font-size: 1.25rem;
    font-weight: 800;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .beacon {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    display: inline-block;
  }
  .beacon-running {
    background-color: var(--accent-green);
    box-shadow: 0 0 10px var(--accent-green);
    animation: pulse 2s infinite;
  }
  .beacon-stopped {
    background-color: var(--text-secondary);
  }
  @keyframes pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(52, 211, 153, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
  }

  .ip-badge {
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 0.75rem;
    color: var(--accent-blue);
    font-family: monospace;
    font-weight: 600;
  }

  /* アクションボタン群 */
  .actions {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 24px;
  }
  .btn {
    width: 100%;
    min-height: 52px;
    border-radius: 12px;
    font-size: 1.02rem;
    font-weight: 700;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    transition: all 0.15s ease;
    text-decoration: none;
    touch-action: manipulation;
  }
  .btn:active {
    transform: scale(0.98);
  }
  .btn-primary {
    background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
    color: #ffffff;
    box-shadow: 0 4px 14px rgba(2, 132, 199, 0.4);
    border: 1px solid #38bdf8;
  }
  .btn-success {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    color: #ffffff;
    box-shadow: 0 4px 14px rgba(5, 150, 105, 0.4);
    border: 1px solid #34d399;
  }
  .btn-secondary {
    background: #1e293b;
    color: #cbd5e1;
    border: 1px solid #334155;
  }
  .btn-danger {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid #dc2626;
  }

  /* メッセージ＆ローディング */
  .toast {
    background: #1e293b;
    border: 1px solid #38bdf8;
    color: #e2e8f0;
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 0.88rem;
    text-align: center;
    margin-bottom: 16px;
    display: none;
  }
  .spinner {
    width: 20px;
    height: 20px;
    border: 3px solid rgba(255,255,255,0.3);
    border-radius: 50%;
    border-top-color: #fff;
    animation: spin 0.8s ease-in-out infinite;
    display: inline-block;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* ガイドカード */
  .guide-card {
    background: #121822;
    border: 1px solid #1f2937;
    border-radius: 12px;
    padding: 14px 16px;
    margin-top: 8px;
    font-size: 0.82rem;
    color: #94a3b8;
    line-height: 1.5;
  }
  .guide-title {
    font-weight: 700;
    color: #e2e8f0;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .guide-card ol {
    margin-left: 20px;
    margin-top: 4px;
  }
  .guide-card li {
    margin-bottom: 4px;
  }
  .code-pill {
    background: #1e293b;
    padding: 2px 6px;
    border-radius: 4px;
    color: #38bdf8;
    font-family: monospace;
    font-size: 0.78rem;
  }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="logo-icon">[NS]</div>
    <div class="title">Nanofiber Studio</div>
    <div class="subtitle">iPhone・モバイル用 リモート起動ポータル</div>
  </div>

  <div class="status-card">
    <div class="status-info">
      <span class="status-label">サーバー状態</span>
      <div class="status-val" id="statusText">
        <span class="beacon beacon-stopped" id="statusBeacon"></span>
        <span id="statusString">確認中...</span>
      </div>
    </div>
    <div class="ip-badge" id="ipBadge">IP: {{LOCAL_IP}}</div>
  </div>

  <div id="toast" class="toast"></div>

  <div class="actions" id="actionButtons">
    <!-- 動的にボタンが挿入されます -->
  </div>

  <div class="guide-card">
    <div class="guide-title">iPhoneのホーム画面に追加してアプリ化</div>
    <ol>
      <li>Safariの画面下部にある <b>共有ボタン（四角から上矢印）</b> をタップ</li>
      <li>メニューから <b>「ホーム画面に追加」</b> を選択</li>
      <li>ホーム画面のアイコンをタップするだけで、いつでもサーバーの起動＆利用が可能になります</li>
    </ol>
  </div>

  <div class="guide-card" style="margin-top: 12px;">
    <div class="guide-title">1タップ起動URL（iOSショートカット対応）</div>
    <p>下記URLを開くだけで自動起動してアプリに遷移します：</p>
    <div style="margin-top: 6px; word-break: break-all;">
      <a href="/start" style="color:#38bdf8; text-decoration:none;" class="code-pill">http://{{LOCAL_IP}}:8500/start</a>
    </div>
  </div>
</div>

<script>
const LOCAL_IP = "{{LOCAL_IP}}";
const APP_URL = "http://" + LOCAL_IP + ":8501";
let isRunning = false;
let isOperating = false;

function showToast(msg) {
  const t = document.getElementById("toast");
  t.innerHTML = msg;
  t.style.display = "block";
}

function hideToast() {
  document.getElementById("toast").style.display = "none";
}

function updateUI(status) {
  isRunning = status.running;
  const sText = document.getElementById("statusString");
  const sBeacon = document.getElementById("statusBeacon");
  const actions = document.getElementById("actionButtons");

  if (isRunning) {
    sText.innerHTML = "稼働中 (Port 8501)";
    sText.style.color = "var(--accent-green)";
    sBeacon.className = "beacon beacon-running";

    actions.innerHTML = `
      <a href="${APP_URL}" class="btn btn-success">
        Nanofiber Studio を開く
      </a>
      <div style="display:flex; gap:10px;">
        <button class="btn btn-secondary" style="flex:1;" onclick="restartServer()">
          再起動
        </button>
        <button class="btn btn-danger" style="flex:1;" onclick="stopServer()">
          停止
        </button>
      </div>
    `;
  } else {
    sText.innerHTML = "停止中";
    sText.style.color = "var(--text-secondary)";
    sBeacon.className = "beacon beacon-stopped";

    actions.innerHTML = `
      <button class="btn btn-primary" onclick="startServer()">
        サーバーを起動する
      </button>
    `;
  }
}

async function fetchStatus() {
  if (isOperating) return;
  try {
    const res = await fetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      updateUI(data);
    }
  } catch (e) {
    document.getElementById("statusString").innerText = "接続待機中...";
  }
}

async function startServer() {
  isOperating = true;
  showToast('<div style="display:flex;align-items:center;justify-content:center;gap:10px;"><div class="spinner"></div><span>サーバーを起動中... (約3〜5秒)</span></div>');
  try {
    const res = await fetch("/api/start");
    const data = await res.json();
    if (data.running) {
      showToast('起動完了！Nanofiber Studio に移動します...');
      setTimeout(() => {
        window.location.href = APP_URL;
      }, 1000);
      return;
    }
  } catch (e) {
    showToast("起動リクエストでエラーが発生しました");
  }
  isOperating = false;
  setTimeout(fetchStatus, 1500);
}

async function stopServer() {
  if (!confirm("Nanofiber Studio サーバーを停止しますか？")) return;
  isOperating = true;
  showToast('<div class="spinner"></div> サーバーを停止中...');
  try {
    await fetch("/api/stop");
    showToast("サーバーを停止しました");
    setTimeout(hideToast, 2500);
  } catch (e) {
    showToast("停止に失敗しました");
  }
  isOperating = false;
  fetchStatus();
}

async function restartServer() {
  if (!confirm("サーバーを再起動しますか？")) return;
  isOperating = true;
  showToast('<div style="display:flex;align-items:center;justify-content:center;gap:10px;"><div class="spinner"></div><span>再起動中...</span></div>');
  try {
    const res = await fetch("/api/restart");
    const data = await res.json();
    if (data.running) {
      showToast('再起動完了！アプリに移動します...');
      setTimeout(() => {
        window.location.href = APP_URL;
      }, 1000);
      return;
    }
  } catch (e) {
    showToast("再起動でエラーが発生しました");
  }
  isOperating = false;
  fetchStatus();
}

// 初期ステータス取得と定期ポーリング
fetchStatus();
setInterval(fetchStatus, 3000);
</script>
</body>
</html>
"""

START_REDIRECT_PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta http-equiv="refresh" content="4;url=http://{{LOCAL_IP}}:8501">
<title>起動中 - Nanofiber Studio</title>
<style>
  body {
    background-color: #0b0f17;
    color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 24px;
  }
  .spinner {
    width: 36px;
    height: 36px;
    border: 4px solid rgba(56, 189, 248, 0.2);
    border-radius: 50%;
    border-top-color: #38bdf8;
    animation: spin 0.8s ease-in-out infinite;
    margin-bottom: 20px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  h2 { font-size: 1.25rem; font-weight: 700; margin-bottom: 8px; }
  p { font-size: 0.88rem; color: #94a3b8; }
  a { color: #38bdf8; text-decoration: none; font-weight: 600; display: inline-block; margin-top: 16px; }
</style>
</head>
<body>
  <div class="spinner"></div>
  <h2>Nanofiber Studio を起動しています</h2>
  <p>準備ができ次第、自動的にアプリへ移動します...</p>
  <a href="http://{{LOCAL_IP}}:8501">自動で移動しない場合はこちらをタップ</a>
</body>
</html>
"""

class LauncherHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # ログ出力を抑制して静かに稼働
        pass

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html_content: str, status: int = 200):
        body = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        local_ip = get_local_ip()
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            page = HTML_PAGE.replace("{{LOCAL_IP}}", local_ip)
            self.send_html(page)

        elif path == "/api/status":
            alive = check_streamlit_alive()
            self.send_json({
                "running": alive,
                "local_ip": local_ip,
                "app_url": f"http://{local_ip}:{PORT_STREAMLIT}",
                "portal_url": f"http://{local_ip}:{PORT_LAUNCHER}"
            })

        elif path == "/api/start":
            start_streamlit_process()
            ready = wait_until_ready(timeout_sec=7.0)
            self.send_json({"success": True, "running": ready})

        elif path == "/api/stop":
            stop_streamlit_process()
            self.send_json({"success": True, "running": False})

        elif path == "/api/restart":
            stop_streamlit_process()
            time.sleep(1)
            start_streamlit_process()
            ready = wait_until_ready(timeout_sec=7.0)
            self.send_json({"success": True, "running": ready})

        elif path == "/start":
            # ブラウザから直接アクセスされた場合：起動してリダイレクトページを表示
            start_streamlit_process()
            page = START_REDIRECT_PAGE.replace("{{LOCAL_IP}}", local_ip)
            self.send_html(page)

        else:
            self.send_response(404)
            self.end_headers()

def run_server(auto_start_app: bool = True):
    local_ip = get_local_ip()
    print("========================================================")
    print("  Nanofiber Studio - iPhone Remote Launcher & Portal")
    print("========================================================")
    print(f"  [Remote Portal URL]   http://{local_ip}:{PORT_LAUNCHER}")
    print(f"  [Direct Start URL]    http://{local_ip}:{PORT_LAUNCHER}/start")
    print(f"  [Nanofiber App URL]   http://{local_ip}:{PORT_STREAMLIT}")
    print("========================================================")

    if auto_start_app and not check_streamlit_alive():
        print(">> Auto-starting Nanofiber Studio (Streamlit)...")
        start_streamlit_process()

    server = HTTPServer(("0.0.0.0", PORT_LAUNCHER), LauncherHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping launcher...")
        server.server_close()

if __name__ == "__main__":
    auto = "--no-auto" not in sys.argv
    run_server(auto_start_app=auto)
