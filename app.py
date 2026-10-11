import streamlit as st
import pandas as pd
import numpy as np
import os
import io
import json
from datetime import datetime
from typing import Optional
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

import database as db
import vision_extractor as vision
import transmittance_analyzer as analyzer
import folder_watcher as watcher

def process_uploaded_image_bytes(raw_bytes: bytes, filename: str) -> tuple[bytes, str]:
    """HEIC/HEIF画像がアップロードされた場合、汎用PNGバイトに安全変換する"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in [".heic", ".heif"]:
        try:
            im = Image.open(io.BytesIO(raw_bytes))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="PNG")
            base_name = os.path.splitext(filename)[0]
            return buf.getvalue(), f"{base_name}.png"
        except Exception:
            return raw_bytes, filename
    return raw_bytes, filename

def get_network_ip() -> str:
    """PCのWi-Fi/LANローカルIPアドレスを取得"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def generate_qr_code_image_bytes(url: str) -> Optional[bytes]:
    """iPhoneで読み取り可能なQRコードPNG画像を生成"""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None

@st.cache_resource
def init_app_database():
    db.init_db()
    return True

init_app_database()

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
SEM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sem_photos")
os.makedirs(SEM_DIR, exist_ok=True)

def load_env_key() -> str:
    """Streamlit Secrets、環境変数、または .env ファイルから API キーを読み込む"""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            k = str(st.secrets["GEMINI_API_KEY"]).strip()
            if k:
                os.environ["GEMINI_API_KEY"] = k
                return k
    except Exception:
        pass

    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        k = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if k:
                            os.environ["GEMINI_API_KEY"] = k
                            return k
        except Exception:
            pass
    return os.environ.get("GEMINI_API_KEY", "")

def save_env_key(key: str) -> bool:
    """.env ファイルに API キーを保存し環境変数にも反映"""
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(f"GEMINI_API_KEY={key.strip()}\n")
        os.environ["GEMINI_API_KEY"] = key.strip()
        return True
    except Exception:
        return False

def safe_clean_path(path: str) -> str:
    """Windowsパスのクォーテーションや空白を安全に除去"""
    if hasattr(watcher, "clean_path"):
        return watcher.clean_path(path)
    return path.strip().strip('"').strip("'") if path else ""

def format_time_ago(created_at_str: str) -> str:
    """作成日時を読みやすい日本語の相対／絶対日時に変換"""
    if not created_at_str:
        return ""
    try:
        dt = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        diff = now - dt
        secs = int(diff.total_seconds())
        if secs < 60:
            return "たった今"
        mins = secs // 60
        if mins < 60:
            return f"{mins}分前"
        hours = mins // 60
        if hours < 24 and dt.date() == now.date():
            return f"{hours}時間前"
        days = diff.days
        if days == 1 or (days == 0 and dt.date() != now.date()):
            return f"昨日 {dt.strftime('%H:%M')}"
        if days < 7:
            return f"{days}日前"
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        return ""

def safe_num(v, default=0.0):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return default if np.isnan(v) else float(v)
    try:
        val = float(v)
        return default if np.isnan(val) else val
    except (ValueError, TypeError):
        return default

def safe_int(v, default=1):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return default if np.isnan(v) else int(v)
    try:
        val = float(v)
        return default if np.isnan(val) else int(val)
    except (ValueError, TypeError):
        return default

def calculate_stretch_summary(params: list) -> dict:
    """各ステップの延伸距離と全体の総延伸距離を計算（欠損値やNaNに対して完全堅牢）"""
    total_um = 0.0
    steps_detailed = []
    for idx, p in enumerate(params or []):
        if not isinstance(p, dict):
            continue
        spd = safe_num(p.get("speed_ums"), 0.0)
        t_start = safe_num(p.get("start_time_s"), 0.0)
        t_stop = safe_num(p.get("stop_time_s"), 0.0)
        duration = max(0.0, t_stop - t_start)
        dist_um = spd * duration
        dist_mm = dist_um / 1000.0
        total_um += dist_um
        step_val = p.get("step")
        step_num = safe_int(step_val, idx + 1)
        steps_detailed.append({
            "step": step_num,
            "current_A": safe_num(p.get("current_A"), 6.0),
            "speed_ums": spd,
            "start_time_s": t_start,
            "stop_time_s": t_stop,
            "distance_mm": round(dist_mm, 2)
        })
    total_mm = total_um / 1000.0
    return {
        "total_um": total_um,
        "total_mm": round(total_mm, 2),
        "steps": steps_detailed
    }

def adjust_steps_count(steps: list, target_count: int) -> list:
    """ステップ数を target_count に増減調整する（追加時は直前の時間を引き継ぐ）"""
    if target_count < 1:
        target_count = 1
    current_list = [dict(s) for s in steps] if steps else []
    if len(current_list) < target_count:
        while len(current_list) < target_count:
            idx = len(current_list) + 1
            if current_list:
                last_step = current_list[-1]
                last_stop = safe_num(last_step.get("stop_time_s"), 0.0)
                last_curr = safe_num(last_step.get("current_A"), 6.0)
                new_step = {
                    "step": idx,
                    "current_A": last_curr,
                    "speed_ums": 0.0,
                    "start_time_s": last_stop,
                    "stop_time_s": last_stop + 60.0
                }
            else:
                new_step = {
                    "step": 1,
                    "current_A": 6.000,
                    "speed_ums": 0.0,
                    "start_time_s": 0.0,
                    "stop_time_s": 60.0
                }
            current_list.append(new_step)
    elif len(current_list) > target_count:
        current_list = current_list[:target_count]

    for i, s in enumerate(current_list):
        s["step"] = i + 1
        s["current_A"] = safe_num(s.get("current_A"), 6.0)
        s["speed_ums"] = safe_num(s.get("speed_ums"), 0.0)
        s["start_time_s"] = safe_num(s.get("start_time_s"), 0.0)
        s["stop_time_s"] = safe_num(s.get("stop_time_s"), 60.0)

    return current_list

def add_step(steps: list) -> list:
    """末尾にステップを1段追加"""
    return adjust_steps_count(steps, len(steps or []) + 1)

def remove_last_step(steps: list) -> list:
    """末尾のステップを1段削除（最低1段残す）"""
    return adjust_steps_count(steps, max(1, len(steps or []) - 1))

def clean_and_normalize_params(params: list) -> list:
    """data_editor の編集結果（NaNやNone）を補正し、step番号を1始まりに整列"""
    cleaned = []
    prev_stop = 0.0
    for idx, p in enumerate(params or []):
        if not isinstance(p, dict):
            continue
        curr = safe_num(p.get("current_A"), 6.0)
        spd = safe_num(p.get("speed_ums"), 0.0)
        t_start = safe_num(p.get("start_time_s"), prev_stop)
        t_stop = safe_num(p.get("stop_time_s"), t_start + 60.0)
        prev_stop = t_stop

        cleaned.append({
            "step": idx + 1,
            "current_A": curr,
            "speed_ums": spd,
            "start_time_s": t_start,
            "stop_time_s": t_stop
        })
    return cleaned

# ページ基本設定（ワイドモード＆フルスクリーン活用）
st.set_page_config(
    page_title="Nanofiber Studio 🔬 ナノ光ファイバ作製管理システム",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# 視認性と実用性を両立するカスタムCSSデザインシステム（ダーク調和＆見切れ防止）
# =========================================================
st.markdown("""
<style>
    /* 全体フォント・レイアウト */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    /* 【重要】上部ヘッダーの重なりと見切れを完全に解消 */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        height: 2.8rem !important;
        z-index: 10 !important;
    }

    .block-container {
        padding-top: 4.2rem !important; /* 上部の見切れを防止する十分なマージン */
        padding-bottom: 3rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    /* =========================================================
       サイドバー (Dark Sleek Lab Sidebar)
       ========================================================= */
    [data-testid="stSidebar"] {
        background-color: #111317 !important;
        border-right: 1px solid #22252d !important;
    }
    
    [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding-top: 1.2rem !important;
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
    }

    /* ブランドヘッダー */
    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 11px;
        padding: 4px 4px 14px 4px;
        border-bottom: 1px solid #22252d;
        margin-bottom: 14px;
    }
    .sidebar-brand-icon {
        width: 32px;
        height: 32px;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        border: 1px solid #334155;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    .sidebar-brand-title {
        font-size: 0.98rem;
        font-weight: 700;
        color: #f8fafc !important;
        letter-spacing: -0.01em;
        line-height: 1.2;
    }
    .sidebar-brand-sub {
        font-size: 0.72rem;
        color: #94a3b8 !important;
        margin-top: 1px;
    }

    /* サイドバーKPI統計カード */
    .sidebar-stats-card {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background-color: #161b24;
        border: 1px solid #283244;
        border-radius: 8px;
        padding: 8px 14px;
        margin-bottom: 12px;
    }
    .sidebar-stat-item {
        text-align: center;
    }
    .sidebar-stat-label {
        display: block;
        font-size: 0.68rem;
        font-weight: 600;
        color: #8b949e !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    .sidebar-stat-val {
        font-size: 1.0rem;
        font-weight: 700;
        color: #f1f5f9 !important;
    }

    /* サイドバーボタン */
    [data-testid="stSidebar"] button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        border: 1px solid #3b82f6 !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        box-shadow: 0 2px 6px rgba(37,99,235,0.3) !important;
        transition: all 0.15s ease !important;
        margin-bottom: 8px !important;
    }
    [data-testid="stSidebar"] button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
        box-shadow: 0 4px 10px rgba(37,99,235,0.45) !important;
    }

    [data-testid="stSidebar"] button[kind="secondary"] {
        background-color: #161b24 !important;
        color: #cbd5e1 !important;
        border: 1px solid #283244 !important;
        border-radius: 7px !important;
        padding: 7px 10px !important;
        font-size: 0.83rem !important;
        font-weight: 600 !important;
        transition: all 0.15s ease !important;
    }
    [data-testid="stSidebar"] button[kind="secondary"]:hover {
        background-color: #202735 !important;
        color: #ffffff !important;
        border-color: #3b475d !important;
    }

    /* サイドバー検索ボックス */
    [data-testid="stSidebar"] [data-testid="stTextInput"] input {
        background-color: #161b24 !important;
        color: #f1f5f9 !important;
        border: 1px solid #283244 !important;
        border-radius: 7px !important;
        font-size: 0.83rem !important;
        padding: 7px 12px !important;
    }
    [data-testid="stSidebar"] [data-testid="stTextInput"] input:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 1px #38bdf8 !important;
    }

    /* ラジオボタン（履歴リスト） */
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
        gap: 3px !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label {
        background-color: transparent !important;
        padding: 8px 11px !important;
        border-radius: 7px !important;
        margin-bottom: 2px !important;
        cursor: pointer !important;
        display: block !important;
        width: 100% !important;
        border: 1px solid transparent !important;
        transition: all 0.15s ease !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:hover {
        background-color: #1c222e !important;
        border-color: #2a3547 !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
        background-color: #1e2838 !important;
        border-color: #384964 !important;
        border-left: 3px solid #38bdf8 !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) span,
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) p {
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label p {
        font-size: 0.84rem !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        margin: 0 !important;
        line-height: 1.4 !important;
        color: #cbd5e1 !important;
    }

    /* =========================================================
       メイン画面コンポーネント（ダーク調和 ＆ 高視認性）
       ========================================================= */

    /* ブラウザ・OSの自動翻訳によるReact DOM破損クラッシュ防止 */
    body, [data-testid="stAppViewContainer"], .main {
        translate: no;
    }

    /* ネイティブコンテナカード (st.container(border=True)) */
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: #141a24 !important;
        border-radius: 10px !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #232d3f !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25) !important;
        margin-bottom: 16px !important;
    }

    /* ラボカード（ダークコンテナ） */
    .lab-card {
        background-color: #141a24 !important;
        border: 1px solid #232d3f !important;
        border-radius: 10px !important;
        padding: 16px 20px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25) !important;
    }

    /* セクションヘッダー */
    .section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 1.0rem;
        font-weight: 700;
        color: #f1f5f9 !important;
        background: #18202d !important;
        border: 1px solid #283449 !important;
        border-left: 4px solid #38bdf8 !important;
        padding: 9px 15px;
        border-radius: 8px;
        margin-bottom: 12px;
    }

    /* 高視認性 KPI メトリクスカード（ダーク） */
    .kpi-card {
        background: #141a24 !important;
        border: 1px solid #232d3f !important;
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.3);
        position: relative;
        overflow: hidden;
    }
    .kpi-card-blue { border-top: 3px solid #38bdf8 !important; }
    .kpi-card-green { border-top: 3px solid #34d399 !important; }
    .kpi-card-amber { border-top: 3px solid #fbbf24 !important; }
    .kpi-card-purple { border-top: 3px solid #c084fc !important; }
    .kpi-card-red { border-top: 3px solid #f87171 !important; }

    .kpi-label {
        font-size: 0.73rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8 !important;
        margin-bottom: 4px;
    }
    .kpi-val {
        font-size: 1.65rem;
        font-weight: 800;
        line-height: 1.15;
        letter-spacing: -0.02em;
    }
    .kpi-sub {
        font-size: 0.74rem;
        color: #64748b !important;
        margin-top: 4px;
        font-weight: 500;
    }

    /* 延伸距離インストルメント・バナー（ダーク） */
    .instrument-banner {
        background: linear-gradient(135deg, #152030 0%, #1b283d 100%) !important;
        border: 1px solid #2b3e5e !important;
        border-radius: 9px;
        padding: 10px 18px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        justify-content: space-around;
        text-align: center;
    }
    .instrument-title {
        font-size: 0.73rem;
        font-weight: 700;
        color: #38bdf8 !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .instrument-val {
        font-size: 1.45rem;
        font-weight: 800;
        color: #60a5fa !important;
        line-height: 1.2;
    }

    /* 破断ステータスバッジ */
    .status-pill-ok {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-size: 0.85rem;
        font-weight: 700;
        color: #34d399 !important;
        background-color: rgba(16, 185, 129, 0.15) !important;
        border: 1px solid #059669 !important;
        padding: 4px 12px;
        border-radius: 9999px;
        vertical-align: middle;
    }
    .status-pill-broken {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-size: 0.85rem;
        font-weight: 700;
        color: #f87171 !important;
        background-color: rgba(239, 68, 68, 0.15) !important;
        border: 1px solid #dc2626 !important;
        padding: 4px 12px;
        border-radius: 9999px;
        vertical-align: middle;
    }

    /* 実験ノート・コールアウト */
    .note-callout {
        background-color: #141b25 !important;
        border-left: 3px solid #475569 !important;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 0.9rem;
        color: #cbd5e1 !important;
        margin-top: 6px;
    }

    /* 歩留まり・同一条件実績カード */
    .yield-card {
        background: linear-gradient(135deg, #131d2a 0%, #152238 100%) !important;
        border: 1px solid #254065 !important;
        border-radius: 9px !important;
        padding: 12px 16px !important;
        margin-bottom: 14px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
    }
    .yield-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        padding-bottom: 6px;
        border-bottom: 1px solid #1e3352;
    }
    .yield-title {
        font-size: 0.94rem;
        font-weight: 700;
        color: #f8fafc !important;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .yield-sub {
        font-size: 0.8rem;
        color: #94a3b8 !important;
    }
    .yield-badge-live {
        background: rgba(30, 58, 95, 0.45) !important;
        border: 1px solid #2563eb !important;
        border-radius: 7px;
        padding: 8px 14px;
        font-size: 0.88rem;
        color: #e2e8f0 !important;
        margin-bottom: 12px;
    }
    .yield-badge-new {
        background: rgba(30, 41, 59, 0.45) !important;
        border: 1px solid #334155 !important;
        border-radius: 7px;
        padding: 8px 14px;
        font-size: 0.88rem;
        color: #94a3b8 !important;
        margin-bottom: 12px;
    }

    /* =========================================================
       iPhone / モバイル端末向けレスポンシブ最適化 (iOS Safari)
       ========================================================= */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 3.2rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.65rem !important;
            padding-right: 0.65rem !important;
        }

        /* iOS Safariの入力タップ時自動ズームを抑止 (16pxルール) */
        input, select, textarea, [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {
            font-size: 16px !important;
        }

        /* デスクトップ用縦マージン空行をモバイルで非表示化（不要な余白ギャップを解消） */
        div[style*="height: 28px"] {
            display: none !important;
        }

        /* モバイルでのタップ領域・ボタンの押しやすさ向上 (Apple HIG準拠) */
        button, [data-testid="baseButton-primary"], [data-testid="baseButton-secondary"] {
            min-height: 42px !important;
            touch-action: manipulation;
        }

        /* 歩留まりカードのグリッドをスマホ向け2列配置に最適化 */
        .yield-card {
            padding: 10px 12px !important;
        }
        .yield-grid-responsive {
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 6px !important;
        }

        /* 延伸インスツルメントバナーを3分割横並びで省スペース・スマート表示 */
        .instrument-banner {
            display: grid !important;
            grid-template-columns: repeat(3, 1fr) !important;
            gap: 4px !important;
            padding: 8px 6px !important;
            text-align: center !important;
        }
        .instrument-banner > div[style*="border-left"] {
            display: none !important;
        }
        .instrument-banner .instrument-title {
            font-size: 0.65rem !important;
            letter-spacing: 0.01em !important;
        }
        .instrument-banner .instrument-val {
            font-size: 1.05rem !important;
            line-height: 1.2 !important;
        }

        /* KPIメトリクスカードを2x2の均等グリッドで配置 */
        [data-testid="stHorizontalBlock"]:has(.kpi-card) {
            display: grid !important;
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 6px !important;
        }
        [data-testid="stHorizontalBlock"]:has(.kpi-card) > [data-testid="stColumn"] {
            width: 100% !important;
            min-width: 0 !important;
            flex: unset !important;
        }
        .kpi-card {
            padding: 8px 10px !important;
            margin-bottom: 0px !important;
        }
        .kpi-label {
            font-size: 0.65rem !important;
            margin-bottom: 2px !important;
        }
        .kpi-val {
            font-size: 1.25rem !important;
        }
        .kpi-sub {
            font-size: 0.65rem !important;
            margin-top: 2px !important;
        }

        /* ラボカード */
        .lab-card {
            padding: 12px 14px !important;
        }

        /* チャート領域のタッチ操作最適化（画面スクロールのスタック防止） */
        [data-testid="stPlotlyChart"] {
            touch-action: pan-y !important;
        }

        /* テーブルの横スクロールを滑らかに */
        [data-testid="stDataFrame"], [data-testid="stTable"] {
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# セッション状態の初期化
if "watch_dir" not in st.session_state:
    st.session_state["watch_dir"] = watcher.DEFAULT_WATCH_DIR
if "api_key" not in st.session_state:
    st.session_state["api_key"] = load_env_key()

if "sample_id" not in st.session_state:
    st.session_state["sample_id"] = f"NF-{datetime.now().strftime('%Y%m%d-%H%M')}"
if "recipe_name" not in st.session_state:
    st.session_state["recipe_name"] = ""
if "notes" not in st.session_state:
    st.session_state["notes"] = "標準作製条件"
if "is_broken" not in st.session_state:
    st.session_state["is_broken"] = 0

if "extracted_params" not in st.session_state:
    st.session_state["extracted_params"] = [
        {"step": 1, "current_A": 6.000, "speed_ums": 0.0, "start_time_s": 0.0, "stop_time_s": 160.0},
        {"step": 2, "current_A": 5.900, "speed_ums": 225.0, "start_time_s": 160.0, "stop_time_s": 230.0},
        {"step": 3, "current_A": 6.000, "speed_ums": 0.0, "start_time_s": 230.0, "stop_time_s": 430.0},
        {"step": 4, "current_A": 5.900, "speed_ums": 225.0, "start_time_s": 430.0, "stop_time_s": 530.0},
    ]
if "params_version" not in st.session_state:
    st.session_state["params_version"] = 0
if "csv_df" not in st.session_state:
    st.session_state["csv_df"] = None
if "csv_stats" not in st.session_state:
    st.session_state["csv_stats"] = {}
if "csv_file_name" not in st.session_state:
    st.session_state["csv_file_name"] = None
if "sem_image_bytes" not in st.session_state:
    st.session_state["sem_image_bytes"] = None
if "sem_image_name" not in st.session_state:
    st.session_state["sem_image_name"] = None
if "selected_record_id" not in st.session_state:
    st.session_state["selected_record_id"] = "NEW"
if "compare_selection" not in st.session_state:
    st.session_state["compare_selection"] = []

# 全レコード取得（CSVデータは除外して高速化）
all_records = db.get_all_records(include_csv_data=False)

# =========================================================
# サイドバー（Antigravity スタイルのダークサイドバー）
# =========================================================
with st.sidebar:
    # 1. ブランドヘッダー
    st.markdown("""
    <div class="sidebar-brand">
        <div class="sidebar-brand-icon">🔬</div>
        <div>
            <div class="sidebar-brand-title">Nanofiber Studio</div>
            <div class="sidebar-brand-sub">光ファイバ作製データ管理</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. メインアクション: 「＋ 新規サンプルの登録」ボタン
    if st.button("＋ 新規サンプルの登録", type="primary", use_container_width=True):
        st.session_state["selected_record_id"] = "NEW"
        st.session_state["sample_id"] = f"NF-{datetime.now().strftime('%Y%m%d-%H%M')}"
        st.session_state["recipe_name"] = ""
        st.session_state["notes"] = "標準作製条件"
        st.session_state["is_broken"] = 0
        st.session_state["sem_image_bytes"] = None
        st.session_state["sem_image_name"] = None
        st.session_state["csv_df"] = None
        st.session_state["csv_stats"] = {}
        st.session_state["csv_file_name"] = None
        if "cached_csv_bytes" in st.session_state:
            del st.session_state["cached_csv_bytes"]
        st.rerun()

    # 3. KPIサマリーカード
    total_cnt = len(all_records)
    intact_cnt = len([r for r in all_records if not r.get("is_broken")])
    broken_cnt = len([r for r in all_records if r.get("is_broken")])
    success_rate = (intact_cnt / total_cnt * 100) if total_cnt > 0 else 0.0

    st.markdown(f"""
    <div class="sidebar-stats-card">
        <div class="sidebar-stat-item">
            <span class="sidebar-stat-label">サンプル数</span>
            <span class="sidebar-stat-val">{total_cnt}件</span>
        </div>
        <div class="sidebar-stat-item">
            <span class="sidebar-stat-label">作製成功率</span>
            <span class="sidebar-stat-val" style="color:#34d399;">{success_rate:.0f}%</span>
        </div>
        <div class="sidebar-stat-item">
            <span class="sidebar-stat-label">破断数</span>
            <span class="sidebar-stat-val" style="color:#f87171;">{broken_cnt}件</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 4. ナビゲーションボタン（横幅十分で省略されない配置）
    if st.button("🕘 最新サンプルを表示", type="secondary", use_container_width=True):
        if all_records:
            st.session_state["selected_record_id"] = all_records[0]["id"]
        st.rerun()

    side_c1, side_c2 = st.columns(2)
    with side_c1:
        if st.button("📊 サンプル比較", type="secondary", use_container_width=True):
            st.session_state["selected_record_id"] = "COMPARE"
            st.rerun()
    with side_c2:
        if st.button("🎯 歩留まり集計", type="secondary", use_container_width=True):
            st.session_state["selected_record_id"] = "YIELD_ANALYSIS"
            st.rerun()

    # 📱 iPhone / スマホ連携 (QRコード & リモート起動)
    with st.expander("📱 iPhone・スマホ接続 ＆ リモート起動", expanded=False):
        net_ip = get_network_ip()
        mobile_url = f"http://{net_ip}:8501"
        launcher_url = f"http://{net_ip}:8500"

        conn_choice = st.radio(
            "接続種別",
            options=["🔬 アプリ (:8501)", "⚡ 起動ポータル (:8500)"],
            horizontal=True,
            label_visibility="collapsed",
            key="sidebar_iphone_view_mode"
        )
        if conn_choice == "🔬 アプリ (:8501)":
            st.markdown(f"""
            <div style="background:#141d2a; border:1px solid #233b5d; border-radius:8px; padding:8px 10px; margin-bottom:8px; text-align:center;">
                <div style="font-size:0.73rem; color:#94a3b8; font-weight:600;">iPhoneアクセス用URL</div>
                <div style="font-size:0.88rem; font-weight:700; color:#38bdf8; word-break:break-all; margin:3px 0;">{mobile_url}</div>
            </div>
            """, unsafe_allow_html=True)
            qr_bytes = generate_qr_code_image_bytes(mobile_url)
            if qr_bytes:
                st.image(qr_bytes, caption="📷 アプリ用 QRコード", use_container_width=True)
            st.markdown("""
            <div style="font-size:0.76rem; color:#94a3b8; line-height:1.4;">
                iPhoneの標準カメラでかざしてSafariで開きます。<br>
                カメラ撮影で条件を即時AI自動認識可能です。
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#141d2a; border:1px solid #1e3a5f; border-radius:8px; padding:8px 10px; margin-bottom:8px; text-align:center;">
                <div style="font-size:0.73rem; color:#94a3b8; font-weight:600;">iPhoneからサーバー起動するURL</div>
                <div style="font-size:0.88rem; font-weight:700; color:#34d399; word-break:break-all; margin:3px 0;">{launcher_url}</div>
            </div>
            """, unsafe_allow_html=True)
            qr_launch = generate_qr_code_image_bytes(launcher_url)
            if qr_launch:
                st.image(qr_launch, caption="⚡ 起動ポータル QRコード", use_container_width=True)
            st.markdown("""
            <div style="font-size:0.76rem; color:#cbd5e1; line-height:1.45;">
                💡 <b>iPhoneからサーバーを立ち上げる方法:</b><br>
                1. このURLをSafariで開く<br>
                2. 画面下の共有ボタンから<b>「ホーム画面に追加」</b><br>
                3. アプリが停止していても、ホーム画面から1タップでPC側サーバーを立ち上げられます。
            </div>
            """, unsafe_allow_html=True)

    st.write("")

    # 5. 実用性向上: サンプル検索ボックス
    search_q = st.text_input(
        "🔍 サンプル検索",
        placeholder="🔍 サンプル名・メモで検索...",
        label_visibility="collapsed",
        key="search_input_box"
    )

    # 6. ステータス別絞り込みタブ
    filter_choice = st.segmented_control(
        "ステータス別絞り込み",
        options=["すべて", "🟢 未破断", "🔴 破断"],
        default="すべて",
        format_func=lambda x: f"すべて ({total_cnt})" if x == "すべて" else (f"🟢 未破断 ({intact_cnt})" if "未破断" in x else f"🔴 破断 ({broken_cnt})"),
        label_visibility="collapsed"
    )

    # フィルタ適用
    if filter_choice == "🟢 未破断":
        filtered_records = [r for r in all_records if not r.get("is_broken")]
    elif filter_choice == "🔴 破断":
        filtered_records = [r for r in all_records if r.get("is_broken")]
    else:
        filtered_records = all_records

    # 検索クエリ適用
    if search_q.strip():
        q_lower = search_q.strip().lower()
        filtered_records = [
            r for r in filtered_records
            if q_lower in str(r.get("sample_id", "")).lower() or q_lower in str(r.get("notes", "")).lower()
        ]

    st.markdown("""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;margin-bottom:6px;">
        <span style="font-size:0.74rem;font-weight:700;color:#94a3b8;letter-spacing:0.04em;text-transform:uppercase;">作製履歴一覧</span>
        <span style="font-size:0.74rem;color:#94a3b8;">{} 件</span>
    </div>
    """.format(len(filtered_records)), unsafe_allow_html=True)

    if not filtered_records:
        st.caption("該当するサンプルがありません。")
    else:
        options = ["NEW"] + [r["id"] for r in filtered_records]
        rec_map = {r["id"]: r for r in filtered_records}

        def format_item(rid):
            if rid == "NEW":
                return "✨ 新規サンプルの登録中"
            r = rec_map.get(rid)
            if not r:
                return f"ID: {rid}"
            s_id = r.get("sample_id", "NF")
            is_b = r.get("is_broken", 0)
            status_dot = "🔴" if is_b else "🟢"
            
            dist = r.get("total_distance_mm")
            dist_str = f"{dist:.1f}mm" if dist is not None else ""
            
            pct = r.get("final_pct")
            pct_str = f"{pct:.0f}%" if pct is not None else ""
            
            has_sem = "🔬" if r.get("sem_photo_path") else ""
            t_ago = format_time_ago(r.get("created_at", ""))
            
            meta = []
            if dist_str:
                meta.append(dist_str)
            if pct_str:
                meta.append(pct_str)
            if has_sem:
                meta.append(has_sem)
            if t_ago:
                meta.append(t_ago)
                
            meta_txt = " · ".join(meta)
            return f"{status_dot} {s_id}  [{meta_txt}]"

        cur_sel = st.session_state.get("selected_record_id", "NEW")
        sel_idx = options.index(cur_sel) if cur_sel in options else 0

        def on_sidebar_record_select():
            chosen = st.session_state.get("sidebar_record_radio")
            if chosen is not None:
                st.session_state["selected_record_id"] = chosen

        st.radio(
            "一覧",
            options=options,
            index=sel_idx,
            format_func=format_item,
            key="sidebar_record_radio",
            on_change=on_sidebar_record_select,
            label_visibility="collapsed"
        )

    # 7. サイドバー最下部: ⚙️ 設定 (Settings)
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    with st.expander("⚙️ 設定 (Settings)", expanded=False):
        st.caption("📁 作製条件写真フォルダ")
        dir_status = watcher.check_watch_dir_status(st.session_state["watch_dir"])
        if dir_status["exists"]:
            st.caption(f"🟢 Google ドライブ接続中: {dir_status['image_count']} 枚")
        else:
            st.caption("🔴 フォルダ未接続")
        watch_dir_input = st.text_input("フォルダパス", value=st.session_state["watch_dir"], label_visibility="collapsed")
        cleaned_dir = safe_clean_path(watch_dir_input)
        if cleaned_dir != st.session_state["watch_dir"]:
            st.session_state["watch_dir"] = cleaned_dir
            st.rerun()

        st.markdown("---")
        st.caption("🔑 Gemini API キー")
        api_key_input = st.text_input("APIキー", value=st.session_state["api_key"], type="password", label_visibility="collapsed", placeholder="AIzaSy...")
        if api_key_input != st.session_state["api_key"]:
            st.session_state["api_key"] = api_key_input
            os.environ["GEMINI_API_KEY"] = api_key_input

        if st.session_state["api_key"]:
            if st.button("💾 APIキーを保存", use_container_width=True):
                if save_env_key(st.session_state["api_key"]):
                    st.toast("✅ APIキーを保存しました！", icon="🔑")

        st.markdown("---")
        st.caption("📦 データのバックアップ ＆ クラウド同期")
        db_raw_bytes = db.get_db_bytes()
        st.download_button(
            "💾 データベース保存 (.db)",
            data=db_raw_bytes,
            file_name=f"nanofiber_backup_{datetime.now().strftime('%Y%m%d')}.db",
            mime="application/x-sqlite3",
            use_container_width=True
        )
        restore_file = st.file_uploader(
            "📥 バックアップから復元",
            type=["db"],
            key="db_restore_uploader",
            help="過去にダウンロードした .db ファイルを選択するとデータを一括復元できます"
        )
        if restore_file is not None:
            if st.button("⚠️ このデータで復元する", type="secondary", use_container_width=True):
                if db.restore_db_from_bytes(restore_file.getvalue()):
                    st.success("✅ データベースを復元しました！")
                    st.rerun()
                else:
                    st.error("❌ データベースの復元に失敗しました。ファイル形式を確認してください。")

        st.markdown("---")
        st.caption("🖥️ デスクトップの「ナノ光ファイバ管理」ショートカットからワンクリック起動可能。")


# =========================================================
# メイン画面（画面幅100%フル活用）
# =========================================================

# ---------------------------------------------------------
# パターン C: 📊 複数サンプルの比較画面
# ---------------------------------------------------------
if st.session_state["selected_record_id"] == "COMPARE":
    col_back, col_title = st.columns([1.2, 5])
    with col_back:
        if st.button("⬅️ 新規・詳細に戻る", use_container_width=True):
            st.session_state["selected_record_id"] = "NEW"
            st.rerun()
    with col_title:
        st.markdown("<h2 style='margin:0;font-weight:800;color:#f8fafc;'>📊 複数サンプルの規格化透過率・作製条件比較</h2>", unsafe_allow_html=True)

    st.write("")

    csv_records = [r for r in all_records if r.get("has_csv") or r.get("csv_data")]
    if not csv_records:
        st.info("比較可能な透過率データを持つサンプルがありません。")
    else:
        rec_labels = {
            r["id"]: f"{'🔴' if r.get('is_broken') else '🟢'} {r['sample_id']} ({r['final_pct']:.1f}%)" if r.get('final_pct') is not None else r['sample_id']
            for r in csv_records
        }
        cur_cmp = st.session_state.get("compare_selection", [])
        valid_default = [cid for cid in cur_cmp if cid in rec_labels]
        if not valid_default and len(csv_records) >= 2:
            valid_default = [csv_records[0]["id"], csv_records[1]["id"]]
        elif not valid_default and len(csv_records) == 1:
            valid_default = [csv_records[0]["id"]]

        selected_cmp = st.multiselect(
            "比較するサンプルを選択",
            options=list(rec_labels.keys()),
            default=valid_default,
            format_func=lambda x: rec_labels.get(x, str(x))
        )
        st.session_state["compare_selection"] = selected_cmp

        raw_cmp_records = [db.get_record_by_id(rid) for rid in selected_cmp]
        cmp_records = [r for r in raw_cmp_records if r and r.get("csv_data")]
        if cmp_records:
            # グラフ比較
            fig_cmp = analyzer.create_comparison_plot(cmp_records, title="規格化透過率推移の重畳比較 (初期受光強度基準: 100%)")
            fig_cmp.update_layout(height=480)
            st.plotly_chart(fig_cmp, use_container_width=True, config={"displayModeBar": False, "responsive": True, "scrollZoom": False})

            # 条件・測定結果の比較一覧
            st.markdown('<div class="section-header"><span>📋 作製条件・光学測定値の比較一覧</span></div>', unsafe_allow_html=True)
            cmp_table_data = []
            for r in cmp_records:
                r_sum = calculate_stretch_summary(r["params"])
                cmp_table_data.append({
                    "延伸結果": "🔴 延伸中破断" if r.get("is_broken") else "🟢 正常終了",
                    "サンプル識別名": r["sample_id"],
                    "総延伸量 ΔL (mm)": f"{r_sum['total_mm']:.2f} mm",
                    "総延伸時間 t (s)": f"{max([p.get('stop_time_s', 0) for p in r['params']]) if r['params'] else 0:.0f} s",
                    "ステップ数": len(r["params"]),
                    "初期受光強度 V₀": f"{r['initial_val']:.4f}" if r.get('initial_val') is not None else "-",
                    "最終透過率 T_final": f"{r['final_pct']:.1f}%" if r.get('final_pct') is not None else "-",
                    "最小透過率 T_min": f"{r['min_pct']:.1f}%" if r.get('min_pct') is not None else "-",
                    "SEM写真": "あり 🔬" if r.get("sem_photo_path") else "なし",
                    "実験備考・所見": r.get("notes", "")
                })
            st.dataframe(pd.DataFrame(cmp_table_data), use_container_width=True, hide_index=True)


# ---------------------------------------------------------
# パターン D: 🎯 作製条件ごとの歩留まり集計ダッシュボード
# ---------------------------------------------------------
elif st.session_state["selected_record_id"] == "YIELD_ANALYSIS":
    col_back, col_title = st.columns([1.2, 5])
    with col_back:
        if st.button("⬅️ 新規・詳細に戻る", use_container_width=True):
            st.session_state["selected_record_id"] = "NEW"
            st.rerun()
    with col_title:
        st.markdown("<h2 style='margin:0;font-weight:800;color:#f8fafc;'>🎯 作製条件別 歩留まり集計 ＆ 実績分析</h2>", unsafe_allow_html=True)

    st.write("")
    all_yield_summary = db.get_all_conditions_yield_summary(all_records)
    if not all_yield_summary:
        st.info("登録済みの作製データがありません。")
    else:
        # KPIサマリーカード
        tot_samples = sum([s["total_count"] for s in all_yield_summary])
        tot_intact = sum([s["intact_count"] for s in all_yield_summary])
        overall_yield = (tot_intact / tot_samples * 100) if tot_samples > 0 else 0.0
        best_yield_cond = max(all_yield_summary, key=lambda x: (x["yield_rate"], x["total_count"]))

        yk1, yk2, yk3, yk4 = st.columns(4)
        with yk1:
            st.markdown(f'<div class="kpi-card kpi-card-blue"><div class="kpi-label">総作製サンプル数</div><div class="kpi-val" style="color:#38bdf8;">{tot_samples} 件</div><div class="kpi-sub">登録済み全サンプル</div></div>', unsafe_allow_html=True)
        with yk2:
            st.markdown(f'<div class="kpi-card kpi-card-purple"><div class="kpi-label">識別レシピ条件数</div><div class="kpi-val" style="color:#c084fc;">{len(all_yield_summary)} 条件</div><div class="kpi-sub">識別済みレシピ群</div></div>', unsafe_allow_html=True)
        with yk3:
            st.markdown(f'<div class="kpi-card kpi-card-green"><div class="kpi-label">全体作製歩留まり</div><div class="kpi-val" style="color:#34d399;">{overall_yield:.1f}%</div><div class="kpi-sub">未破断率 ({tot_intact}/{tot_samples})</div></div>', unsafe_allow_html=True)
        with yk4:
            st.markdown(f'<div class="kpi-card kpi-card-amber"><div class="kpi-label">最高歩留まり条件</div><div class="kpi-val" style="font-size:0.95rem; color:#fbbf24; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{best_yield_cond["condition_name"]}</div><div class="kpi-sub">歩留まり: {best_yield_cond["yield_rate"]:.1f}% ({best_yield_cond["total_count"]}件)</div></div>', unsafe_allow_html=True)

        st.write("")
        st.markdown('<div class="section-header"><span>📋 作製条件別・歩留まり集計一覧</span></div>', unsafe_allow_html=True)

        table_data = []
        for s in all_yield_summary:
            avg_f_str = f"{s['avg_final_pct']:.1f}%" if s['avg_final_pct'] is not None else "-"
            if s['avg_final_pct'] is not None and s['std_final_pct'] > 0:
                avg_f_str += f" ± {s['std_final_pct']:.1f}%"
            loss_str = f"{s['avg_loss_db']:.2f} dB" if s['avg_loss_db'] is not None else "-"
            dist_str = f"{s['avg_dist_mm']:.2f} mm" if s['avg_dist_mm'] is not None else "-"
            sample_names = ", ".join([f"{'🔴' if sm['is_broken'] else '🟢'}{sm['sample_id']}" for sm in s["samples"]])
            table_data.append({
                "作製条件名 (レシピ)": s["condition_name"],
                "ステップ数": s["step_count"],
                "平均総延伸量 ΔL": dist_str,
                "試行数 (件)": s["total_count"],
                "正常終了 (件)": s["intact_count"],
                "破断 (件)": s["broken_count"],
                "未破断歩留まり (%)": f"{s['yield_rate']:.1f}%",
                "平均最終透過率 (%)": avg_f_str,
                "平均光挿入損失": loss_str,
                "高透過率歩留まり (≥80%)": f"{s['high_yield_rate_80']:.1f}%",
                "作製サンプル一覧": sample_names
            })

        df_summary = pd.DataFrame(table_data)
        st.dataframe(df_summary, use_container_width=True, hide_index=True)

        # CSVダウンロード
        csv_bytes = df_summary.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 条件別歩留まり集計データ (CSV) をダウンロード",
            data=csv_bytes,
            file_name=f"nanofiber_yield_summary_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )

        st.write("")
        # Plotlyグラフ
        import plotly.graph_objects as go
        cond_labels = [s["condition_name"] for s in all_yield_summary]
        yield_vals = [s["yield_rate"] for s in all_yield_summary]
        final_vals = [s["avg_final_pct"] if s["avg_final_pct"] is not None else 0 for s in all_yield_summary]

        fig_yield = go.Figure()
        fig_yield.add_trace(go.Bar(
            name="作製歩留まり (未破断率 %)",
            x=cond_labels,
            y=yield_vals,
            marker_color="#34d399",
            text=[f"{y:.1f}%" for y in yield_vals],
            textposition="auto"
        ))
        fig_yield.add_trace(go.Bar(
            name="平均最終透過率 (%)",
            x=cond_labels,
            y=final_vals,
            marker_color="#38bdf8",
            text=[f"{f:.1f}%" if f > 0 else "-" for f in final_vals],
            textposition="auto"
        ))
        fig_yield.update_layout(
            title="作製条件別 歩留まり ＆ 平均最終透過率の比較",
            barmode="group",
            yaxis=dict(title="パーセンテージ (%)", range=[0, 105]),
            template="plotly_dark",
            paper_bgcolor="#141a24",
            plot_bgcolor="#18202d",
            font=dict(color="#f1f5f9"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=60, b=40),
            height=400
        )
        st.plotly_chart(fig_yield, use_container_width=True, config={"displayModeBar": False, "responsive": True, "scrollZoom": False})


# ---------------------------------------------------------
# パターン A: 📝 新規作製データの登録画面
# ---------------------------------------------------------
elif st.session_state["selected_record_id"] == "NEW":
    st.markdown("<h2 style='margin:0 0 12px 0;font-weight:800;color:#f8fafc;'>📝 新規サンプルの作製・登録</h2>", unsafe_allow_html=True)

    # トップコントロールカード
    with st.container(border=True):
        top1, top2, top3, top4, top5 = st.columns([1.9, 1.8, 1.6, 2.7, 1.4], gap="medium")
        with top1:
            st.session_state["sample_id"] = st.text_input(
                "🏷️ サンプル識別名 (Sample ID)",
                value=st.session_state["sample_id"]
            )
        with top2:
            st.session_state["recipe_name"] = st.text_input(
                "📋 作製条件名 (Recipe)",
                value=st.session_state.get("recipe_name", ""),
                placeholder="例: 標準条件A, 4段延伸",
                help="同一の条件名または同一パラメータのサンプル間で歩留まりが自動集計されます"
            )
        with top3:
            broken_choice = st.radio(
                "⚡ 延伸結果 (破断有無)",
                ["🟢 正常終了（未破断）", "🔴 延伸中破断"],
                horizontal=True,
                index=1 if st.session_state.get("is_broken", 0) else 0,
                key="is_broken_selector_new"
            )
            st.session_state["is_broken"] = 1 if "🔴" in broken_choice else 0
        with top4:
            st.session_state["notes"] = st.text_input(
                "📝 実験備考・所見",
                value=st.session_state["notes"],
                placeholder="加熱炉配置、ファイバ仕様、実験所見など"
            )
        with top5:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            save_clicked_top = st.button("💾 【 作製データを保存 】", type="primary", use_container_width=True, key="save_btn_top")

    # 現在の条件の過去歩留まり・実績バナー
    cur_cond_stats = db.get_condition_yield_stats(all_records, st.session_state["extracted_params"], st.session_state.get("recipe_name", ""))
    cond_lbl = db.get_condition_label(st.session_state["extracted_params"], st.session_state.get("recipe_name", ""))
    
    if cur_cond_stats["total_count"] > 0:
        c_rate = cur_cond_stats["yield_rate"]
        c_color = "#34d399" if c_rate >= 80 else ("#fbbf24" if c_rate >= 50 else "#f87171")
        avg_f_str = f"{cur_cond_stats['avg_final_pct']:.1f}%" if cur_cond_stats['avg_final_pct'] is not None else "-"
        st.markdown(f"""
        <div class="yield-badge-live">
            🎯 <b>同一作製条件（{cond_lbl}）の実績・歩留まり</b>: 
            試行数 <b>{cur_cond_stats['total_count']} 件</b> ｜ 
            未破断歩留まり: <b style="color:{c_color};">{c_rate:.1f}%</b> (未破断: {cur_cond_stats['intact_count']}件 / 破断: {cur_cond_stats['broken_count']}件) ｜ 
            平均最終透過率: <b>{avg_f_str}</b>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="yield-badge-new">
            💡 <b>この作製条件（{cond_lbl}）は初回試行（登録数: 0件）です</b>（保存後に同一条件の歩留まりが自動集計されます）
        </div>
        """, unsafe_allow_html=True)

    # 左右2列のフルワイドレイアウト
    c_left, c_right = st.columns([1, 1], gap="large")

    # 【左列】条件パラメータ ＆ SEM写真
    with c_left:
        st.markdown('<div class="section-header"><span>📋 1. 作製条件パラメータ</span></div>', unsafe_allow_html=True)

        with st.expander("📷 モニタ写真から作製条件を自動抽出 (AI OCR)", expanded=True):
            r_c1, r_c2 = st.columns([2, 1])
            with r_c1:
                src_type = st.radio(
                    "入力ソース選択",
                    ["📂 Google ドライブから選択", "📤 写真ファイルをアップロード"],
                    horizontal=True,
                    label_visibility="collapsed"
                )

            img_bytes_to_read = None
            if src_type == "📂 Google ドライブから選択":
                g_images = watcher.get_image_files_in_dir(st.session_state["watch_dir"])
                if g_images:
                    g_opts = {f"{it['filename']} ({it['modified_at']})": it["path"] for it in g_images}
                    sel_g = st.selectbox("写真ファイル", list(g_opts.keys()), label_visibility="collapsed")
                    if sel_g:
                        try:
                            with open(g_opts[sel_g], "rb") as f:
                                img_bytes_to_read = f.read()
                        except Exception:
                            pass
                else:
                    st.caption(f"`{st.session_state['watch_dir']}` に画像がありません。")

            elif src_type == "📤 写真ファイルをアップロード":
                up_p = st.file_uploader("写真ファイルを選択", type=["jpg", "jpeg", "png", "bmp", "webp", "heic", "heif"], label_visibility="collapsed")
                if up_p is not None:
                    img_bytes_to_read = up_p.getvalue()

            with r_c2:
                if img_bytes_to_read:
                    if st.button("⚡ 写真から条件を自動抽出", type="primary", use_container_width=True):
                        if not st.session_state["api_key"]:
                            st.error("左側サイドバーの設定で Gemini API キーを設定してください。")
                        else:
                            with st.spinner("AIによる作製条件パラメータ解析中..."):
                                res = vision.extract_conditions_from_image(img_bytes_to_read, api_key=st.session_state["api_key"])
                                if res["success"]:
                                    st.session_state["extracted_params"] = res["data"]
                                    st.session_state["params_version"] += 1
                                    st.toast(f"✅ {len(res['data'])} ステップの作製条件を抽出しました！", icon="✨")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {res['error']}")

        # 延伸距離サマリー計算
        cur_params = st.session_state.get("extracted_params") or []
        s_sum = calculate_stretch_summary(cur_params)

        # 総延伸距離インストルメント・バナー
        st.markdown(f"""
        <div class="instrument-banner">
            <div>
                <div class="instrument-title">📏 総延伸量 ΔL</div>
                <div class="instrument-val">{s_sum['total_mm']:.2f} mm <span style="font-size:0.92rem;color:#94a3b8;font-weight:600;">({s_sum['total_um']:,.0f} µm)</span></div>
            </div>
            <div style="border-left: 1px solid #2b3e5e; height: 32px;"></div>
            <div>
                <div class="instrument-title">⏱️ 総延伸時間 t_total</div>
                <div class="instrument-val" style="color:#f1f5f9;">{max([p.get('stop_time_s', 0) for p in cur_params]) if cur_params else 0:.0f} s</div>
            </div>
            <div style="border-left: 1px solid #2b3e5e; height: 32px;"></div>
            <div>
                <div class="instrument-title">🔢 ステップ数</div>
                <div class="instrument-val" style="color:#f1f5f9;">{len(cur_params)} ステップ</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ステップ数コントロールバー（段数の直接変更・1段追加・末尾削除）
        st.markdown("<div style='margin-top: 10px; margin-bottom: 6px;'></div>", unsafe_allow_html=True)
        sc_col1, sc_col2, sc_col3 = st.columns([1.5, 1.25, 1.25], gap="small")
        with sc_col1:
            step_cnt_input = st.number_input(
                "🔢 ステップ数",
                min_value=1,
                max_value=30,
                value=len(cur_params),
                step=1,
                key=f"new_step_count_num_{st.session_state['params_version']}",
                help="ステップ数を変更できます。増やすと直前の条件を引き継いだステップが追加されます。"
            )
            if step_cnt_input != len(cur_params):
                st.session_state["extracted_params"] = adjust_steps_count(cur_params, step_cnt_input)
                st.session_state["params_version"] += 1
                st.rerun()

        with sc_col2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("➕ ステップ追加", key=f"btn_add_step_new_{st.session_state['params_version']}", use_container_width=True):
                st.session_state["extracted_params"] = add_step(cur_params)
                st.session_state["params_version"] += 1
                st.rerun()

        with sc_col3:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("➖ 最後のステップを削除", key=f"btn_del_step_new_{st.session_state['params_version']}", use_container_width=True, disabled=(len(cur_params) <= 1)):
                st.session_state["extracted_params"] = remove_last_step(cur_params)
                st.session_state["params_version"] += 1
                st.rerun()

        # 延伸パラメータ編集表
        detailed_df = pd.DataFrame(s_sum["steps"])
        editor_key = f"params_editor_{st.session_state['params_version']}"
        edited_df = st.data_editor(
            detailed_df,
            key=editor_key,
            column_config={
                "step": st.column_config.NumberColumn("ステップ No.", format="%d", min_value=1, step=1, width="small"),
                "current_A": st.column_config.NumberColumn("加熱電流 I (A)", format="%.3f A"),
                "speed_ums": st.column_config.NumberColumn("延伸速度 v (µm/s)", format="%.0f µm/s"),
                "start_time_s": st.column_config.NumberColumn("開始時刻 t_start (s)", format="%.1f s"),
                "stop_time_s": st.column_config.NumberColumn("終了時刻 t_stop (s)", format="%.1f s"),
                "distance_mm": st.column_config.NumberColumn("延伸量 ΔL (mm)", format="%.2f mm", disabled=True),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )
        cleaned_from_table = clean_and_normalize_params(edited_df.drop(columns=["distance_mm"], errors="ignore").to_dict(orient="records"))
        if len(cleaned_from_table) != len(cur_params):
            st.session_state["extracted_params"] = cleaned_from_table
            st.session_state["params_version"] += 1
            st.rerun()
        else:
            st.session_state["extracted_params"] = cleaned_from_table

        st.write("")

        # SEM写真の追加
        st.markdown('<div class="section-header"><span>🔬 2. SEM写真（電子顕微鏡観察）の追加</span></div>', unsafe_allow_html=True)
        sem_up = st.file_uploader(
            "SEM写真をここにドラッグ＆ドロップ",
            type=["jpg", "jpeg", "png", "bmp", "tif", "tiff", "heic", "heif"],
            help="完成したナノ光ファイバのSEM（走査型電子顕微鏡）写真を登録・保存できます"
        )
        if sem_up is not None:
            conv_bytes, conv_name = process_uploaded_image_bytes(sem_up.getvalue(), sem_up.name)
            st.session_state["sem_image_bytes"] = conv_bytes
            st.session_state["sem_image_name"] = conv_name

        if st.session_state.get("sem_image_bytes"):
            try:
                sem_pil = Image.open(io.BytesIO(st.session_state["sem_image_bytes"]))
                st.image(sem_pil, caption=f"選択中のSEM写真: {st.session_state.get('sem_image_name', 'SEM画像')}", width="stretch")
                if st.button("🗑️ SEM写真をクリア", type="secondary"):
                    st.session_state["sem_image_bytes"] = None
                    st.session_state["sem_image_name"] = None
                    st.rerun()
            except Exception:
                st.warning("SEM画像の読み込みに失敗しました。")

    # 【右列】透過率CSV ＆ 規格化グラフ
    with c_right:
        st.markdown('<div class="section-header"><span>📈 3. 透過率推移 ＆ 規格化グラフ (初期受光強度基準 100%)</span></div>', unsafe_allow_html=True)

        up_csv = st.file_uploader("透過率CSVをここにドラッグ＆ドロップ", type=["csv", "txt", "dat"], label_visibility="collapsed")

        raw_df = None
        if up_csv is not None:
            st.session_state["csv_file_name"] = up_csv.name
            st.session_state["cached_csv_bytes"] = up_csv.getvalue()

        if "cached_csv_bytes" in st.session_state:
            p_df, p_err = analyzer.parse_transmittance_csv(st.session_state["cached_csv_bytes"])
            if not p_err:
                raw_df = p_df

        if raw_df is not None:
            num_cols = list(raw_df.select_dtypes(include=[np.number]).columns)
            t_col = num_cols[0] if len(num_cols) > 0 else raw_df.columns[0]
            v_col = num_cols[1] if len(num_cols) > 1 else t_col

            try:
                norm_df, stats = analyzer.calculate_normalized_transmittance(raw_df, time_col=t_col, val_col=v_col, baseline_mode="first")
                st.session_state["csv_df"] = norm_df
                st.session_state["csv_stats"] = stats

                init_v = stats['initial_val']
                f_pct = stats['final_pct']
                m_pct = stats['min_pct']
                loss_db = stats['final_loss_db']

                # 透過率の推移から破断(急落)を自動判定して選択
                if st.session_state.get("is_broken_auto_file") != st.session_state.get("csv_file_name"):
                    if f_pct < 5.0 or m_pct < 2.0:
                        st.session_state["is_broken"] = 1
                    else:
                        st.session_state["is_broken"] = 0
                    st.session_state["is_broken_auto_file"] = st.session_state.get("csv_file_name")

                # 高視認性 4大メトリクス（ダーク調和）
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    st.markdown(f'<div class="kpi-card kpi-card-blue"><div class="kpi-label">初期受光強度 V₀</div><div class="kpi-val" style="color:#38bdf8;">{init_v:.4f}</div><div class="kpi-sub">基準受光値 (V)</div></div>', unsafe_allow_html=True)
                with m2:
                    color_final = "#34d399" if f_pct >= 80 else ("#fbbf24" if f_pct >= 50 else "#f87171")
                    type_final = "kpi-card-green" if f_pct >= 80 else ("kpi-card-amber" if f_pct >= 50 else "kpi-card-red")
                    st.markdown(f'<div class="kpi-card {type_final}"><div class="kpi-label">最終透過率 T_final</div><div class="kpi-val" style="color:{color_final};">{f_pct:.1f}%</div><div class="kpi-sub">規格化最終値</div></div>', unsafe_allow_html=True)
                with m3:
                    st.markdown(f'<div class="kpi-card kpi-card-amber"><div class="kpi-label">最小透過率 T_min</div><div class="kpi-val" style="color:#fbbf24;">{m_pct:.1f}%</div><div class="kpi-sub">延伸中最小値</div></div>', unsafe_allow_html=True)
                with m4:
                    st.markdown(f'<div class="kpi-card kpi-card-purple"><div class="kpi-label">光学挿入損失</div><div class="kpi-val" style="color:#c084fc;">{loss_db:.2f}dB</div><div class="kpi-sub">Insertion Loss (dB)</div></div>', unsafe_allow_html=True)

                st.write("")

                fig = analyzer.create_transmittance_plot(
                    norm_df,
                    time_col=t_col,
                    conditions=st.session_state.get("extracted_params"),
                    title=f"{st.session_state.get('csv_file_name', '透過率推移')} (初期受光強度基準: 100%)",
                    show_stages=True
                )
                fig.update_layout(height=480)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True, "scrollZoom": False})

                c_exp = norm_df[[t_col, "transmittance_pct", "loss_db"]].to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 規格化透過率データ (CSV) をダウンロード",
                    data=c_exp,
                    file_name=f"normalized_{st.session_state.get('sample_id', 'NF')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            except Exception as ex:
                st.error(f"透過率の解析エラー: {str(ex)}")
        else:
            st.info("ここに透過率CSVファイルをドラッグ＆ドロップしてください。グラフが自動で描画されます。")

    st.markdown("---")
    save_clicked_bottom = st.button("💾 【 作製データを保存 】", type="primary", use_container_width=True, key="save_btn_bottom")

    # 保存実行処理
    if save_clicked_top or save_clicked_bottom:
        save_name = st.session_state.get("sample_id", "").strip() or f"NF-{datetime.now().strftime('%Y%m%d-%H%M')}"
        save_notes = st.session_state.get("notes", "")
        save_broken = int(st.session_state.get("is_broken", 0))
        save_params = st.session_state.get("extracted_params") or []
        save_stats = st.session_state.get("csv_stats") or {}
        save_norm_df = st.session_state.get("csv_df")
        save_csv_p = st.session_state.get("csv_file_name") or ""
        save_dist_s = calculate_stretch_summary(save_params)

        saved_sem_p = None
        if st.session_state.get("sem_image_bytes"):
            ext = os.path.splitext(st.session_state.get("sem_image_name", "sem.png"))[1] or ".png"
            sem_fname = f"{save_name}_sem{ext}"
            saved_sem_p = os.path.join(SEM_DIR, sem_fname)
            try:
                with open(saved_sem_p, "wb") as f:
                    f.write(st.session_state["sem_image_bytes"])
            except Exception:
                saved_sem_p = None

        c_cache = None
        if save_norm_df is not None:
            t_cols = [c for c in save_norm_df.columns if c not in ["transmittance_pct", "loss_db"]]
            col_t = t_cols[0] if t_cols else save_norm_df.columns[0]
            c_cache = {
                "time": save_norm_df[col_t].tolist(),
                "pct": save_norm_df["transmittance_pct"].tolist()
            }

        new_rec_id = db.save_record(
            sample_id=save_name,
            params=save_params,
            photo_path="",
            csv_path=save_csv_p,
            csv_data=c_cache,
            initial_val=save_stats.get("initial_val"),
            final_pct=save_stats.get("final_pct"),
            min_pct=save_stats.get("min_pct"),
            notes=save_notes,
            sem_photo_path=saved_sem_p,
            total_distance_mm=save_dist_s["total_mm"],
            is_broken=save_broken,
            recipe_name=st.session_state.get("recipe_name", "").strip()
        )
        st.session_state["selected_record_id"] = new_rec_id
        st.toast(f"🎉 サンプル「{save_name}」を保存しました！", icon="💾")
        st.rerun()



# ---------------------------------------------------------
# パターン B: 📋 選択した過去サンプルの詳細表示 ＆ 【直接編集モード】
# ---------------------------------------------------------
else:
    rec = db.get_record_by_id(st.session_state["selected_record_id"])
    if not rec:
        st.warning("選択されたレコードが見つかりません。")
        st.session_state["selected_record_id"] = "NEW"
        st.rerun()
    else:
        rec_id = rec["id"]
        rec_params = rec["params"]
        is_b = int(rec.get("is_broken", 0))

        # =========================================================
        # 1. ヘッダー部（編集ボタン不要！その場ですぐに直接変更可能）
        # =========================================================
        with st.container(border=True):
            top1, top2, top3, top4, top5 = st.columns([1.9, 1.8, 1.6, 2.7, 1.4], gap="medium")
            with top1:
                cur_sample_id = st.text_input(
                    "🏷️ サンプル識別名 (Sample ID)",
                    value=rec["sample_id"],
                    key=f"rec_sample_id_{rec_id}",
                    help="サンプル識別名を編集して保存できます"
                )
            with top2:
                cur_recipe_name = st.text_input(
                    "📋 作製条件名 (Recipe)",
                    value=rec.get("recipe_name", ""),
                    key=f"rec_recipe_{rec_id}",
                    placeholder="例: 標準条件A, 4段延伸",
                    help="同一の条件名または同一パラメータのサンプル間で歩留まりが自動集計されます"
                )
            with top3:
                broken_val = st.radio(
                    "⚡ 延伸結果 (破断有無)",
                    ["🟢 正常終了（未破断）", "🔴 延伸中破断"],
                    index=1 if is_b else 0,
                    horizontal=True,
                    key=f"rec_broken_radio_{rec_id}"
                )
                is_broken_edited = 1 if "🔴" in broken_val else 0
            with top4:
                cur_notes = st.text_input(
                    "📝 実験備考・所見",
                    value=rec.get("notes", ""),
                    key=f"rec_notes_{rec_id}",
                    placeholder="加熱炉配置、ファイバ仕様、実験所見など"
                )
            with top5:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                save_detail_top = st.button("💾 【 変更内容を保存 】", type="primary", use_container_width=True, key=f"save_rec_top_{rec_id}")

        # サブアクションバー（登録日時、複製、削除）
        sub_c1, sub_c2 = st.columns([1.8, 1.2])
        with sub_c1:
            status_html = f"<span class='status-pill-broken'>🔴 延伸中破断</span>" if is_broken_edited else f"<span class='status-pill-ok'>🟢 正常終了</span>"
            st.markdown(f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'><span style='font-size:1.1rem;font-weight:700;color:#f8fafc;'>レコード #{rec_id}</span>{status_html}<span style='color:#94a3b8;font-size:0.83rem;'>登録日時: {rec['created_at']}</span></div>", unsafe_allow_html=True)
        with sub_c2:
            act1, act2 = st.columns([1.3, 0.9])
            with act1:
                if st.button("📋 この作製条件を複製して新規作成", use_container_width=True, key=f"btn_clone_{rec_id}"):
                    st.session_state["extracted_params"] = st.session_state.get(f"rec_params_{rec_id}", rec["params"])
                    st.session_state["params_version"] += 1
                    st.session_state["sample_id"] = f"{cur_sample_id.strip()}-rev"
                    st.session_state["recipe_name"] = cur_recipe_name.strip()
                    st.session_state["notes"] = f"ベース: {cur_sample_id.strip()}"
                    st.session_state["is_broken"] = 0
                    st.session_state["selected_record_id"] = "NEW"
                    st.session_state["csv_df"] = None
                    st.session_state["csv_stats"] = {}
                    st.session_state["csv_file_name"] = None
                    st.session_state["sem_image_bytes"] = None
                    st.session_state["sem_image_name"] = None
                    if "cached_csv_bytes" in st.session_state:
                        del st.session_state["cached_csv_bytes"]
                    st.rerun()
            with act2:
                if st.button("🗑️ 削除", type="secondary", use_container_width=True, key=f"btn_del_{rec_id}"):
                    db.delete_record(rec_id)
                    st.session_state["selected_record_id"] = "NEW"
                    st.toast("データを削除しました", icon="🗑️")
                    st.rerun()

        # パラメータ取得
        rec_params_key = f"rec_params_{rec_id}"
        rec_ver_key = f"rec_ver_{rec_id}"
        if rec_params_key not in st.session_state:
            st.session_state[rec_params_key] = rec["params"]
        if rec_ver_key not in st.session_state:
            st.session_state[rec_ver_key] = 0

        cur_rec_params = st.session_state[rec_params_key]
        cur_rec_ver = st.session_state[rec_ver_key]

        # 同一条件での歩留まり集計
        cond_stats = db.get_condition_yield_stats(all_records, cur_rec_params, cur_recipe_name)
        cond_label = db.get_condition_label(cur_rec_params, cur_recipe_name)
        total_same = cond_stats["total_count"]
        y_rate = cond_stats["yield_rate"]
        y_color = "#34d399" if y_rate >= 80 else ("#fbbf24" if y_rate >= 50 else "#f87171")
        avg_f_val = cond_stats["avg_final_pct"]
        avg_f_txt = f"{avg_f_val:.1f}%" if avg_f_val is not None else "-"
        if avg_f_val is not None and cond_stats["std_final_pct"] > 0:
            avg_f_txt += f" ± {cond_stats['std_final_pct']:.1f}%"
        avg_loss_txt = f"{cond_stats['avg_loss_db']:.2f} dB" if cond_stats["avg_loss_db"] is not None else "-"
        high_80_txt = f"{cond_stats['high_yield_rate_80']:.1f}%" if total_same > 0 else "-"

        st.markdown(f"""
        <div class="yield-card">
            <div class="yield-header">
                <div class="yield-title">
                    <span>🎯 同一作製条件の実績 ＆ 歩留まり:</span>
                    <span style="color:#38bdf8;">{cond_label}</span>
                </div>
                <div class="yield-sub">同条件作製数: <b>計 {total_same} サンプル</b></div>
            </div>
            <div class="yield-grid-responsive" style="display:grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 8px;">
                <div class="kpi-card kpi-card-blue" style="padding:8px 12px; margin-bottom:0;">
                    <div class="kpi-label">総作製サンプル数</div>
                    <div class="kpi-val" style="font-size:1.15rem; color:#38bdf8;">{total_same} 件</div>
                    <div class="kpi-sub">未破断 {cond_stats['intact_count']}件 / 破断 {cond_stats['broken_count']}件</div>
                </div>
                <div class="kpi-card {'kpi-card-green' if y_rate>=80 else ('kpi-card-amber' if y_rate>=50 else 'kpi-card-red')}" style="padding:8px 12px; margin-bottom:0;">
                    <div class="kpi-label">作製歩留まり (未破断率)</div>
                    <div class="kpi-val" style="font-size:1.15rem; color:{y_color};">{y_rate:.1f}%</div>
                    <div class="kpi-sub">正常終了率</div>
                </div>
                <div class="kpi-card kpi-card-amber" style="padding:8px 12px; margin-bottom:0;">
                    <div class="kpi-label">平均最終透過率 T_avg</div>
                    <div class="kpi-val" style="font-size:1.15rem; color:#fbbf24;">{avg_f_txt}</div>
                    <div class="kpi-sub">未破断サンプル平均</div>
                </div>
                <div class="kpi-card kpi-card-purple" style="padding:8px 12px; margin-bottom:0;">
                    <div class="kpi-label">高透過率歩留まり (T ≥ 80%)</div>
                    <div class="kpi-val" style="font-size:1.15rem; color:#c084fc;">{high_80_txt}</div>
                    <div class="kpi-sub">平均光学損失: {avg_loss_txt}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if total_same > 1:
            st.markdown("<div style='font-size:0.8rem; font-weight:600; color:#94a3b8; margin-top:6px; margin-bottom:4px;'>📌 同一条件作製サンプル一覧:</div>", unsafe_allow_html=True)
            pills_cols = st.columns(min(total_same, 5))
            for p_idx, s_info in enumerate(cond_stats["samples"][:5]):
                col_target = pills_cols[p_idx % len(pills_cols)]
                with col_target:
                    s_icon = "🔴" if s_info["is_broken"] else "🟢"
                    s_pct = f"{s_info['final_pct']:.0f}%" if s_info["final_pct"] is not None else ("破断" if s_info["is_broken"] else "-")
                    is_this = (s_info["id"] == rec_id)
                    btn_text = f"{'👉 ' if is_this else ''}{s_icon} {s_info['sample_id']} ({s_pct})"
                    if st.button(btn_text, key=f"btn_jump_same_{s_info['id']}_{rec_id}", disabled=is_this, use_container_width=True):
                        st.session_state["selected_record_id"] = s_info["id"]
                        st.rerun()

        st.write("")

        # 左右2列のフルワイドレイアウト
        d_col_left, d_col_right = st.columns([1, 1], gap="large")

        # 【左列】作製条件パラメータ（直接編集テーブル） ＆ SEM写真
        with d_col_left:
            st.markdown('<div class="section-header"><span>📋 1. 作製条件パラメータ（表内で直接編集可能）</span></div>', unsafe_allow_html=True)

            cur_rec_sum = calculate_stretch_summary(cur_rec_params)

            # 延伸距離インストルメント・バナー（リアルタイム自動再計算）
            st.markdown(f"""
            <div class="instrument-banner">
                <div>
                    <div class="instrument-title">📏 総延伸量 ΔL</div>
                    <div class="instrument-val">{cur_rec_sum['total_mm']:.2f} mm <span style="font-size:0.92rem;color:#94a3b8;font-weight:600;">({cur_rec_sum['total_um']:,.0f} µm)</span></div>
                </div>
                <div style="border-left: 1px solid #2b3e5e; height: 32px;"></div>
                <div>
                    <div class="instrument-title">⏱️ 総延伸時間 t_total</div>
                    <div class="instrument-val" style="color:#f1f5f9;">{max([p.get('stop_time_s', 0) for p in cur_rec_params]) if cur_rec_params else 0:.0f} s</div>
                </div>
                <div style="border-left: 1px solid #2b3e5e; height: 32px;"></div>
                <div>
                    <div class="instrument-title">🔢 ステップ数</div>
                    <div class="instrument-val" style="color:#f1f5f9;">{len(cur_rec_params)} ステップ</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ステップ数コントロールバー（段数の直接変更・1段追加・末尾削除）
            st.markdown("<div style='margin-top: 10px; margin-bottom: 6px;'></div>", unsafe_allow_html=True)
            sc_r1, sc_r2, sc_r3 = st.columns([1.5, 1.25, 1.25], gap="small")
            with sc_r1:
                step_cnt_rec = st.number_input(
                    "🔢 ステップ数",
                    min_value=1,
                    max_value=30,
                    value=len(cur_rec_params),
                    step=1,
                    key=f"rec_step_cnt_num_{rec_id}_{cur_rec_ver}",
                    help="ステップ数を変更できます。増やすと直前の条件を引き継いだステップが追加されます。"
                )
                if step_cnt_rec != len(cur_rec_params):
                    st.session_state[rec_params_key] = adjust_steps_count(cur_rec_params, step_cnt_rec)
                    st.session_state[rec_ver_key] += 1
                    st.rerun()

            with sc_r2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("➕ ステップ追加", key=f"btn_add_step_rec_{rec_id}_{cur_rec_ver}", use_container_width=True):
                    st.session_state[rec_params_key] = add_step(cur_rec_params)
                    st.session_state[rec_ver_key] += 1
                    st.rerun()

            with sc_r3:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("➖ 最後のステップを削除", key=f"btn_del_step_rec_{rec_id}_{cur_rec_ver}", use_container_width=True, disabled=(len(cur_rec_params) <= 1)):
                    st.session_state[rec_params_key] = remove_last_step(cur_rec_params)
                    st.session_state[rec_ver_key] += 1
                    st.rerun()

            # 直接編集可能な data_editor（ボタンを押さずにそのまま直接編集可能！）
            edit_df = pd.DataFrame(cur_rec_sum["steps"])
            edited_df = st.data_editor(
                edit_df,
                key=f"params_editor_rec_{rec_id}_{cur_rec_ver}",
                column_config={
                    "step": st.column_config.NumberColumn("ステップ No.", format="%d", min_value=1, step=1, width="small"),
                    "current_A": st.column_config.NumberColumn("加熱電流 I (A)", format="%.3f A"),
                    "speed_ums": st.column_config.NumberColumn("延伸速度 v (µm/s)", format="%.0f µm/s"),
                    "start_time_s": st.column_config.NumberColumn("開始時刻 t_start (s)", format="%.1f s"),
                    "stop_time_s": st.column_config.NumberColumn("終了時刻 t_stop (s)", format="%.1f s"),
                    "distance_mm": st.column_config.NumberColumn("延伸量 ΔL (mm)", format="%.2f mm", disabled=True),
                },
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True
            )

            cleaned_rec_table = clean_and_normalize_params(edited_df.drop(columns=["distance_mm"], errors="ignore").to_dict(orient="records"))
            if len(cleaned_rec_table) != len(cur_rec_params):
                st.session_state[rec_params_key] = cleaned_rec_table
                st.session_state[rec_ver_key] += 1
                st.rerun()
            else:
                st.session_state[rec_params_key] = cleaned_rec_table

            updated_params = cleaned_rec_table
            updated_sum = calculate_stretch_summary(updated_params)

            st.write("")

            # 2. SEM写真
            st.markdown('<div class="section-header"><span>🔬 2. SEM写真（電子顕微鏡観察）</span></div>', unsafe_allow_html=True)
            cur_sem_path = rec.get("sem_photo_path")
            delete_sem_flag = False

            if cur_sem_path and os.path.exists(cur_sem_path):
                try:
                    sem_image_obj = Image.open(cur_sem_path)
                    st.image(sem_image_obj, caption=f"登録SEM写真: {os.path.basename(cur_sem_path)}", width="stretch")
                    delete_sem_flag = st.checkbox("🗑️ このSEM写真を削除する（保存時に反映）", key=f"chk_del_sem_{rec_id}")
                except Exception:
                    st.warning("SEM写真の表示に失敗しました。")

            new_sem_file = st.file_uploader(
                "新しいSEM写真をアップロードして登録・差し替え",
                type=["jpg", "jpeg", "png", "bmp", "tif", "tiff", "heic", "heif"],
                key=f"rec_sem_up_{rec_id}"
            )

        # 【右列】透過率グラフ ＆ CSV
        with d_col_right:
            st.markdown('<div class="section-header"><span>📈 3. 透過率推移 ＆ 規格化グラフ (初期受光強度基準 100%)</span></div>', unsafe_allow_html=True)

            new_csv_file = st.file_uploader(
                "新しい透過率CSVファイルをアップロードして差し替え",
                type=["csv", "txt", "dat"],
                key=f"rec_csv_up_{rec_id}"
            )

            display_df = None
            display_stats = {}
            new_csv_cache = None
            new_csv_name = rec.get("csv_path")

            if new_csv_file is not None:
                p_df, p_err = analyzer.parse_transmittance_csv(new_csv_file.getvalue())
                if not p_err and len(p_df) > 0:
                    num_cols = list(p_df.select_dtypes(include=[np.number]).columns)
                    t_col = num_cols[0] if len(num_cols) > 0 else p_df.columns[0]
                    v_col = num_cols[1] if len(num_cols) > 1 else t_col
                    norm_df, stats = analyzer.calculate_normalized_transmittance(p_df, time_col=t_col, val_col=v_col, baseline_mode="first")
                    display_df = norm_df
                    display_stats = stats
                    new_csv_name = new_csv_file.name
                    new_csv_cache = {
                        "time": norm_df[t_col].tolist(),
                        "pct": norm_df["transmittance_pct"].tolist()
                    }
                    st.success(f"新しいCSV「{new_csv_file.name}」を解析しました（保存時に反映）。")
            elif rec.get("csv_data"):
                c_dict = rec["csv_data"]
                display_df = pd.DataFrame({
                    "Time (s)": c_dict["time"],
                    "transmittance_pct": c_dict["pct"]
                })
                display_stats = {
                    "initial_val": rec.get("initial_val"),
                    "final_pct": rec.get("final_pct"),
                    "min_pct": rec.get("min_pct")
                }
                new_csv_cache = rec["csv_data"]

            if display_df is not None:
                iv = display_stats.get("initial_val")
                fp = display_stats.get("final_pct")
                mp = display_stats.get("min_pct")

                # 4大高視認性 KPI メトリクスカード
                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    init_s = f"{iv:.4f}" if iv is not None else "-"
                    st.markdown(f'<div class="kpi-card kpi-card-blue"><div class="kpi-label">初期受光強度 V₀</div><div class="kpi-val" style="color:#38bdf8;">{init_s}</div><div class="kpi-sub">基準受光値 (V)</div></div>', unsafe_allow_html=True)
                with k2:
                    color_final = "#f87171" if is_broken_edited or (fp is not None and fp < 50) else ("#fbbf24" if (fp is not None and fp < 80) else "#34d399")
                    type_final = "kpi-card-red" if is_broken_edited else ("kpi-card-amber" if (fp is not None and fp < 80) else "kpi-card-green")
                    final_s = f"{fp:.1f}%" if fp is not None else "-"
                    st.markdown(f'<div class="kpi-card {type_final}"><div class="kpi-label">最終透過率 T_final</div><div class="kpi-val" style="color:{color_final};">{final_s}</div><div class="kpi-sub">規格化最終値</div></div>', unsafe_allow_html=True)
                with k3:
                    min_s = f"{mp:.1f}%" if mp is not None else "-"
                    st.markdown(f'<div class="kpi-card kpi-card-amber"><div class="kpi-label">最小透過率 T_min</div><div class="kpi-val" style="color:#fbbf24;">{min_s}</div><div class="kpi-sub">延伸中最小値</div></div>', unsafe_allow_html=True)
                with k4:
                    if fp is not None and fp > 0:
                        l_db = -10.0 * np.log10(max(fp / 100.0, 1e-6))
                        loss_txt = f"{l_db:.2f} dB"
                    else:
                        loss_txt = "破断" if is_broken_edited else "-"
                    st.markdown(f'<div class="kpi-card kpi-card-purple"><div class="kpi-label">光学挿入損失</div><div class="kpi-val" style="color:#c084fc;">{loss_txt}</div><div class="kpi-sub">Insertion Loss (dB)</div></div>', unsafe_allow_html=True)

                st.write("")
                t_name = [c for c in display_df.columns if c != "transmittance_pct"][0] if len(display_df.columns) > 1 else display_df.columns[0]
                fig_disp = analyzer.create_transmittance_plot(
                    display_df,
                    time_col=t_name,
                    conditions=updated_params,
                    title=f"{cur_sample_id} の規格化透過率推移 (初期受光強度基準: 100%)",
                    show_stages=True
                )
                fig_disp.update_layout(height=450)
                st.plotly_chart(fig_disp, use_container_width=True, config={"displayModeBar": False, "responsive": True, "scrollZoom": False})

                # CSVダウンロード
                rec_csv_data = display_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 規格化透過率データ (CSV) をダウンロード",
                    data=rec_csv_data,
                    file_name=f"normalized_{cur_sample_id.strip() or 'NF'}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("このレコードには透過率CSVデータがまだ登録されていません。上のアップローダーから追加できます。")

        st.markdown("---")
        save_detail_bottom = st.button("💾 【 変更内容を保存 】", type="primary", use_container_width=True, key=f"save_rec_bot_{rec_id}")

        # 保存実行処理
        if save_detail_top or save_detail_bottom:
            final_sem_path = cur_sem_path
            if delete_sem_flag:
                final_sem_path = None
            elif new_sem_file is not None:
                sem_bytes, sem_name = process_uploaded_image_bytes(new_sem_file.getvalue(), new_sem_file.name)
                ext = os.path.splitext(sem_name)[1] or ".png"
                sem_fname = f"{cur_sample_id.strip()}_sem{ext}"
                final_sem_path = os.path.join(SEM_DIR, sem_fname)
                with open(final_sem_path, "wb") as f:
                    f.write(sem_bytes)

            db.update_record(
                record_id=rec_id,
                sample_id=cur_sample_id.strip() or rec["sample_id"],
                params=updated_params,
                notes=cur_notes,
                is_broken=is_broken_edited,
                total_distance_mm=updated_sum["total_mm"],
                sem_photo_path=final_sem_path,
                csv_path=new_csv_name,
                csv_data=new_csv_cache,
                initial_val=display_stats.get("initial_val"),
                final_pct=display_stats.get("final_pct"),
                min_pct=display_stats.get("min_pct"),
                recipe_name=cur_recipe_name.strip()
            )
            st.toast(f"🎉 サンプル「{cur_sample_id.strip()}」を保存しました！", icon="💾")
            st.rerun()

