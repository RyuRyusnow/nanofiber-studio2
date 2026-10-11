import os
from typing import List, Dict, Any
from datetime import datetime
import streamlit as st

DEFAULT_WATCH_DIR = r"G:\マイドライブ\parameter photo"

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif"}

def clean_path(path: str) -> str:
    """Windows Explorer からのコピペ等で混入するダブルクォーテーションや空白を除去"""
    if not path:
        return ""
    return path.strip().strip('"').strip("'")

@st.cache_data(ttl=10, show_spinner=False)
def get_image_files_in_dir(directory: str = DEFAULT_WATCH_DIR) -> List[Dict[str, Any]]:
    """
    指定フォルダ内の画像ファイル一覧を取得（更新日時が新しい順にソート）
    """
    dir_path = clean_path(directory)
    if not dir_path or not os.path.exists(dir_path):
        return []

    results = []
    try:
        entries = os.listdir(dir_path)
    except Exception:
        return []

    for name in entries:
        ext = os.path.splitext(name)[1].lower()
        if ext in VALID_EXTENSIONS:
            full_path = os.path.join(dir_path, name)
            try:
                if os.path.isfile(full_path):
                    stat = os.stat(full_path)
                    mod_time = datetime.fromtimestamp(stat.st_mtime)
                    results.append({
                        "filename": name,
                        "path": full_path,
                        "size_bytes": stat.st_size,
                        "modified_at": mod_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "mtime": stat.st_mtime
                    })
            except Exception:
                pass

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results

@st.cache_data(ttl=10, show_spinner=False)
def check_watch_dir_status(directory: str = DEFAULT_WATCH_DIR) -> Dict[str, Any]:
    """監視フォルダの状態をチェック"""
    dir_path = clean_path(directory)
    exists = os.path.exists(dir_path) if dir_path else False
    count = 0
    if exists:
        try:
            images = get_image_files_in_dir(dir_path)
            count = len(images)
        except Exception:
            pass

    return {
        "directory": dir_path,
        "exists": exists,
        "image_count": count
    }
