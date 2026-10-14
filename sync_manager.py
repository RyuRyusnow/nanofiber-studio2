import os
import sys
import json
import shutil
import sqlite3
import math
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

DB_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB_PATH = os.path.join(DB_DIR, "nanofiber_data.db")
LOCAL_SEM_DIR = os.path.join(DB_DIR, "sem_photos")
LOCAL_SAMPLE_DIR = os.path.join(DB_DIR, "sample_data")
LOCAL_BACKUP_JSON = os.path.join(DB_DIR, "nanofiber_local_backup.json")
TOMBSTONES_FILE = os.path.join(DB_DIR, "nanofiber_tombstones.json")

# 可能な Google Drive / クラウド共有同期パスの候補リスト
POTENTIAL_SYNC_PATHS = [
    r"G:\マイドライブ\nanofiber_sync",
    r"G:\My Drive\nanofiber_sync",
    os.path.join(os.environ.get("USERPROFILE", ""), "Google Drive", "nanofiber_sync"),
    os.path.join(os.environ.get("USERPROFILE", ""), "GoogleDrive", "nanofiber_sync"),
    os.path.join(os.environ.get("USERPROFILE", ""), "マイドライブ", "nanofiber_sync"),
    r"G:\その他のパソコン\nanofiber_sync",
]

def load_tombstones() -> set:
    """削除されたレコードのキー一覧（墓石）をロード"""
    if os.path.exists(TOMBSTONES_FILE):
        try:
            with open(TOMBSTONES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                elif isinstance(data, dict):
                    return set(data.get("deleted_keys", []))
        except Exception:
            pass
    return set()

def save_tombstones(tombstones: set) -> None:
    """削除されたレコードのキー一覧を保存"""
    try:
        with open(TOMBSTONES_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(tombstones)), f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def unregister_tombstone(sample_id: str, fab_date: str = "", created_at: str = "") -> None:
    """レコードが新規作成・保存された際、過去の削除墓石を解除"""
    key = make_record_key(sample_id, fab_date, created_at)
    s_clean = str(sample_id or "").strip().lower()
    tombstones = load_tombstones()
    changed = False
    if key in tombstones:
        tombstones.remove(key)
        changed = True
    if s_clean in tombstones:
        tombstones.remove(s_clean)
        changed = True
    if changed:
        save_tombstones(tombstones)

def register_record_deletion(sample_id: str, fab_date: str = "", created_at: str = "", db_path: str = LOCAL_DB_PATH, sync_dir: Optional[str] = None) -> None:
    """レコード削除を登録し、クラウドマスターおよび共有DBからも即座に消去"""
    key = make_record_key(sample_id, fab_date, created_at)
    s_clean = str(sample_id or "").strip().lower()
    tombstones = load_tombstones()
    tombstones.add(key)
    tombstones.add(s_clean)
    save_tombstones(tombstones)

    s_dir = sync_dir or get_shared_sync_dir()
    master_json_path = os.path.join(s_dir, "nanofiber_sync_master.json")
    if os.path.exists(master_json_path):
        try:
            with open(master_json_path, "r", encoding="utf-8") as f:
                cloud_data = json.load(f)
            if isinstance(cloud_data, dict):
                recs = cloud_data.get("records", [])
                filtered = [
                    r for r in recs
                    if make_record_key(r.get("sample_id"), r.get("fabrication_date"), r.get("created_at")) != key
                    and str(r.get("sample_id") or "").strip().lower() != s_clean
                ]
                cloud_data["records"] = filtered
                cloud_deleted = set(cloud_data.get("deleted_keys", []))
                cloud_deleted.add(key)
                cloud_deleted.add(s_clean)
                cloud_data["deleted_keys"] = sorted(list(cloud_deleted))
                cloud_data["total_records"] = len(filtered)
                cloud_data["last_synced_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(master_json_path, "w", encoding="utf-8") as f:
                    json.dump(cloud_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # クラウド共有SQLiteデータベース(nanofiber_shared.db)からも即時削除
    shared_db_path = os.path.join(s_dir, "nanofiber_shared.db")
    if os.path.exists(shared_db_path):
        try:
            with sqlite3.connect(shared_db_path) as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM fabrication_records WHERE LOWER(sample_id) = ?", (s_clean,))
                conn.commit()
        except Exception:
            pass

    # ローカルバックアップJSONからも即時削除
    if os.path.exists(LOCAL_BACKUP_JSON):
        try:
            with open(LOCAL_BACKUP_JSON, "r", encoding="utf-8") as f:
                lb_data = json.load(f)
            if isinstance(lb_data, dict):
                recs = lb_data.get("records", [])
                filtered = [
                    r for r in recs
                    if make_record_key(r.get("sample_id"), r.get("fabrication_date"), r.get("created_at")) != key
                    and str(r.get("sample_id") or "").strip().lower() != s_clean
                ]
                lb_data["records"] = filtered
                lb_deleted = set(lb_data.get("deleted_keys", []))
                lb_deleted.add(key)
                lb_deleted.add(s_clean)
                lb_data["deleted_keys"] = sorted(list(lb_deleted))
                lb_data["total_records"] = len(filtered)
                lb_data["last_synced_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(LOCAL_BACKUP_JSON, "w", encoding="utf-8") as f:
                    json.dump(lb_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def clean_for_json(obj: Any) -> Any:
    """NaN や Inf など非準拠の浮動小数点数を安全に None / 0.0 に変換"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    return obj

def get_shared_sync_dir(custom_path: Optional[str] = None) -> str:
    """利用可能なクラウド / 共有同期ディレクトリを取得または初期化"""
    if custom_path and os.path.isdir(custom_path):
        os.makedirs(custom_path, exist_ok=True)
        return os.path.abspath(custom_path)

    # 環境変数での指定確認
    env_p = os.environ.get("NANOFIBER_SYNC_DIR")
    if env_p and os.path.isdir(env_p):
        os.makedirs(env_p, exist_ok=True)
        return os.path.abspath(env_p)

    # Google Drive 等の外部同期パスを検出
    for p in POTENTIAL_SYNC_PATHS:
        try:
            drive_root = os.path.splitdrive(p)[0]
            if drive_root and os.path.exists(drive_root):
                parent_dir = os.path.dirname(p)
                if os.path.exists(parent_dir):
                    os.makedirs(p, exist_ok=True)
                    return os.path.abspath(p)
        except Exception:
            continue

    # いずれも使えない場合はローカルの shared_sync フォルダにフォールバック
    fallback = os.path.join(DB_DIR, "shared_sync")
    os.makedirs(fallback, exist_ok=True)
    return os.path.abspath(fallback)

def get_sync_media_dir(sync_dir: Optional[str] = None) -> str:
    """同期メディア（SEM写真、モニタ写真等）の保存ディレクトリ"""
    s_dir = sync_dir or get_shared_sync_dir()
    media_dir = os.path.join(s_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    return media_dir

def resolve_media_file(filename_or_path: Optional[str], sync_dir: Optional[str] = None) -> Optional[str]:
    """
    複数PC間で異なる絶対パスを吸収し、ローカルまたはクラウドメディアから実ファイルを探す。
    見つかった場合はローカルSEMフォルダへ必要に応じてコピーし、使用可能なローカルパスを返す。
    """
    if not filename_or_path:
        return None
    raw_str = str(filename_or_path).strip()
    if not raw_str:
        return None

    # 1. 指定パスがそのままローカルに存在する場合
    if os.path.exists(raw_str):
        return os.path.abspath(raw_str)

    # 2. ファイル名のみを抽出してローカル各フォルダ内を探索
    fname = os.path.basename(raw_str)
    candidate_local_sem = os.path.join(LOCAL_SEM_DIR, fname)
    if os.path.exists(candidate_local_sem):
        return os.path.abspath(candidate_local_sem)

    candidate_sample = os.path.join(LOCAL_SAMPLE_DIR, fname)
    if os.path.exists(candidate_sample):
        return os.path.abspath(candidate_sample)

    # 3. クラウド / 共有同期メディアフォルダ内を探索
    media_dir = get_sync_media_dir(sync_dir)
    candidate_cloud = os.path.join(media_dir, fname)
    if os.path.exists(candidate_cloud):
        try:
            os.makedirs(LOCAL_SEM_DIR, exist_ok=True)
            shutil.copy2(candidate_cloud, candidate_local_sem)
            return os.path.abspath(candidate_local_sem)
        except Exception:
            return os.path.abspath(candidate_cloud)

    return None

def copy_media_to_sync(src_path: Optional[str], sync_dir: Optional[str] = None) -> Optional[str]:
    """ローカルの写真ファイルをクラウド共有メディアフォルダにコピーし、ファイル名を返す"""
    if not src_path or not os.path.exists(src_path):
        return None
    try:
        media_dir = get_sync_media_dir(sync_dir)
        fname = os.path.basename(src_path)
        dest_path = os.path.join(media_dir, fname)
        if not os.path.exists(dest_path) or os.path.getmtime(src_path) > os.path.getmtime(dest_path):
            shutil.copy2(src_path, dest_path)
        return fname
    except Exception:
        return os.path.basename(src_path)

def make_record_key(sample_id: str, fab_date: str, created_at: str) -> str:
    """レコードを一意に識別するキー（PC間のID番号重複を防止）"""
    s_clean = str(sample_id or "").strip().lower()
    d_clean = str(fab_date or "").strip()
    c_clean = str(created_at or "").strip()[:10]
    return f"{s_clean}___{d_clean or c_clean}"

def sync_with_cloud(
    db_path: str = LOCAL_DB_PATH,
    custom_sync_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    ローカルSQLiteデータベースとクラウド（Google Drive）共有同期マスターとの完全双方向マージ。
    他PCで追加・編集されたレコードを安全に取り込み、ローカルの変更もクラウドに送信します。
    """
    import database as db_mod

    sync_dir = get_shared_sync_dir(custom_sync_dir)
    master_json_path = os.path.join(sync_dir, "nanofiber_sync_master.json")
    shared_db_path = os.path.join(sync_dir, "nanofiber_shared.db")

    # 1. 削除墓石（tombstones）の読み込みと統合
    tombstones = load_tombstones()
    cloud_deleted = set()
    cloud_records = []
    if os.path.exists(master_json_path):
        try:
            with open(master_json_path, "r", encoding="utf-8") as f:
                cloud_data = json.load(f)
                if isinstance(cloud_data, dict):
                    cloud_records = cloud_data.get("records", [])
                    cloud_deleted = set(cloud_data.get("deleted_keys", []))
                elif isinstance(cloud_data, list):
                    cloud_records = cloud_data
        except Exception:
            cloud_records = []

    merged_tombstones = tombstones | cloud_deleted
    save_tombstones(merged_tombstones)

    # クラウド側が空で shared_db_path が存在する場合はそちらからも補完
    if not cloud_records and os.path.exists(shared_db_path):
        try:
            cloud_records = db_mod.get_all_records(include_csv_data=True, db_path=shared_db_path)
        except Exception:
            pass

    # 2. ローカルレコードを全件取得（CSVデータも含む）
    local_records = db_mod.get_all_records(include_csv_data=True, db_path=db_path)

    # ローカル辞書マップの構築（削除済み墓石に該当するものはローカルDBからも抹消）
    local_map = {}
    for r in local_records:
        k = make_record_key(r.get("sample_id"), r.get("fabrication_date"), r.get("created_at"))
        s_clean = str(r.get("sample_id") or "").strip().lower()
        if k in merged_tombstones or s_clean in merged_tombstones:
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.cursor().execute("DELETE FROM fabrication_records WHERE id = ?", (r["id"],))
                    conn.commit()
            except Exception:
                pass
        else:
            local_map[k] = r

    # 3. 双方向スマートマージの実行
    pulled_count = 0
    pushed_count = 0
    updated_local_count = 0

    # (A) クラウドレコードをローカルに取り込み（削除墓石は厳格に除外）
    for cr in cloud_records:
        c_sid = cr.get("sample_id", "")
        c_clean = str(c_sid).strip().lower()
        c_fdate = cr.get("fabrication_date") or cr.get("created_at", "")[:10]
        c_cat = cr.get("created_at", "")
        c_key = make_record_key(c_sid, c_fdate, c_cat)

        if c_key in merged_tombstones or c_clean in merged_tombstones:
            continue

        # メディア写真ファイルのローカル解決
        sem_f = cr.get("sem_photo_file") or cr.get("sem_photo_path")
        resolved_sem = resolve_media_file(sem_f, sync_dir)

        if c_key not in local_map:
            # ローカルに存在しない -> 新規INSERT
            db_mod.save_record(
                sample_id=c_sid,
                params=cr.get("params", []),
                photo_path=cr.get("photo_path", ""),
                csv_path=cr.get("csv_path", ""),
                csv_data=cr.get("csv_data"),
                initial_val=cr.get("initial_val"),
                final_pct=cr.get("final_pct"),
                min_pct=cr.get("min_pct"),
                notes=cr.get("notes", ""),
                sem_photo_path=resolved_sem,
                total_distance_mm=cr.get("total_distance_mm"),
                is_broken=int(cr.get("is_broken", 0)),
                recipe_name=cr.get("recipe_name", ""),
                fabrication_date=c_fdate,
                temperature=cr.get("temperature", ""),
                db_path=db_path
            )
            pulled_count += 1
        else:
            # 既に存在する場合: クラウド側にCSVデータがあり、ローカルに無い場合は更新
            lr = local_map[c_key]
            needs_update = False
            l_csv = lr.get("csv_data")
            c_csv = cr.get("csv_data")
            if not l_csv and c_csv:
                needs_update = True
            if not lr.get("sem_photo_path") and resolved_sem:
                needs_update = True
            if not lr.get("recipe_name") and cr.get("recipe_name"):
                needs_update = True
            if not lr.get("temperature") and cr.get("temperature"):
                needs_update = True

            if needs_update:
                db_mod.update_record(
                    record_id=lr["id"],
                    sample_id=lr.get("sample_id"),
                    params=lr.get("params") or cr.get("params", []),
                    notes=lr.get("notes") or cr.get("notes", ""),
                    is_broken=int(lr.get("is_broken") or cr.get("is_broken", 0)),
                    total_distance_mm=lr.get("total_distance_mm") or cr.get("total_distance_mm"),
                    sem_photo_path=lr.get("sem_photo_path") or resolved_sem,
                    csv_path=lr.get("csv_path") or cr.get("csv_path"),
                    csv_data=l_csv or c_csv,
                    initial_val=lr.get("initial_val") or cr.get("initial_val"),
                    final_pct=lr.get("final_pct") or cr.get("final_pct"),
                    min_pct=lr.get("min_pct") or cr.get("min_pct"),
                    recipe_name=lr.get("recipe_name") or cr.get("recipe_name"),
                    fabrication_date=lr.get("fabrication_date") or c_fdate,
                    temperature=lr.get("temperature") or cr.get("temperature"),
                    db_path=db_path
                )
                updated_local_count += 1

    # (B) 取り込み後の全ローカルレコードを取得してクラウド側マスターを再構築
    merged_local_records = db_mod.get_all_records(include_csv_data=True, db_path=db_path)
    export_list = []

    for lr in merged_local_records:
        k = make_record_key(lr.get("sample_id"), lr.get("fabrication_date"), lr.get("created_at"))
        s_clean = str(lr.get("sample_id") or "").strip().lower()
        if k in merged_tombstones or s_clean in merged_tombstones:
            continue

        sem_p = lr.get("sem_photo_path")
        sem_filename = None
        if sem_p:
            sem_filename = copy_media_to_sync(sem_p, sync_dir)

        export_list.append(clean_for_json({
            "sample_id": lr.get("sample_id"),
            "created_at": lr.get("created_at"),
            "fabrication_date": lr.get("fabrication_date"),
            "recipe_name": lr.get("recipe_name"),
            "temperature": lr.get("temperature"),
            "is_broken": int(lr.get("is_broken", 0)),
            "total_distance_mm": lr.get("total_distance_mm"),
            "notes": lr.get("notes"),
            "params": lr.get("params"),
            "csv_path": lr.get("csv_path"),
            "csv_data": lr.get("csv_data"),
            "initial_val": lr.get("initial_val"),
            "final_pct": lr.get("final_pct"),
            "min_pct": lr.get("min_pct"),
            "sem_photo_file": sem_filename,
            "photo_path": lr.get("photo_path")
        }))

    # クラウド側に新しく追加されたローカル件数の概算
    if len(cloud_records) < len(export_list):
        pushed_count = len(export_list) - len(cloud_records)

    # (C) マスター JSON の書き出し (Google Drive & ローカルバックアップ)
    master_payload = {
        "schema_version": 2,
        "last_synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "synced_by_host": os.environ.get("COMPUTERNAME", "PC"),
        "total_records": len(export_list),
        "deleted_keys": sorted(list(merged_tombstones)),
        "records": export_list
    }

    try:
        with open(master_json_path, "w", encoding="utf-8") as f:
            json.dump(master_payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        pass

    try:
        with open(LOCAL_BACKUP_JSON, "w", encoding="utf-8") as f:
            json.dump(master_payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # (D) クラウド共有DB (SQLite) も念のため同期保存
    try:
        shutil.copy2(db_path, shared_db_path)
    except Exception:
        pass

    return {
        "success": True,
        "sync_dir": sync_dir,
        "is_google_drive": ("マイドライブ" in sync_dir or "Google" in sync_dir),
        "pulled_count": pulled_count,
        "updated_count": updated_local_count,
        "pushed_count": pushed_count,
        "total_records": len(export_list),
        "last_synced_at": master_payload["last_synced_at"]
    }

def export_all_records_json(db_path: str = LOCAL_DB_PATH) -> str:
    """全作製レコードを JSON 文字列としてエクスポート"""
    import database as db_mod
    records = db_mod.get_all_records(include_csv_data=True, db_path=db_path)
    clean_records = [clean_for_json(r) for r in records]
    payload = {
        "schema_version": 2,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exported_by": os.environ.get("COMPUTERNAME", "PC"),
        "total_records": len(clean_records),
        "records": clean_records
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

def import_records_from_json(json_content_or_dict: Any, db_path: str = LOCAL_DB_PATH) -> Dict[str, Any]:
    """外部から受け取った JSON 文字列または辞書からレコードを取り込み・マージ"""
    import database as db_mod

    if isinstance(json_content_or_dict, str):
        try:
            data = json.loads(json_content_or_dict)
        except Exception as e:
            return {"success": False, "error": f"JSON解析失敗: {str(e)}"}
    elif isinstance(json_content_or_dict, dict):
        data = json_content_or_dict
    elif isinstance(json_content_or_dict, list):
        data = {"records": json_content_or_dict}
    else:
        return {"success": False, "error": "無効なデータ形式です"}

    records = data.get("records", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    if not records:
        return {"success": False, "error": "有効な作製レコードが含まれていません"}

    local_records = db_mod.get_all_records(include_csv_data=True, db_path=db_path)
    local_map = {}
    for r in local_records:
        k = make_record_key(r.get("sample_id"), r.get("fabrication_date"), r.get("created_at"))
        local_map[k] = r

    imported_cnt = 0
    updated_cnt = 0

    for r in records:
        sid = r.get("sample_id", "")
        fdate = r.get("fabrication_date") or r.get("created_at", "")[:10]
        cat = r.get("created_at", "")
        k = make_record_key(sid, fdate, cat)

        if k not in local_map:
            db_mod.save_record(
                sample_id=sid,
                params=r.get("params", []),
                photo_path=r.get("photo_path", ""),
                csv_path=r.get("csv_path", ""),
                csv_data=r.get("csv_data"),
                initial_val=r.get("initial_val"),
                final_pct=r.get("final_pct"),
                min_pct=r.get("min_pct"),
                notes=r.get("notes", ""),
                sem_photo_path=r.get("sem_photo_path"),
                total_distance_mm=r.get("total_distance_mm"),
                is_broken=int(r.get("is_broken", 0)),
                recipe_name=r.get("recipe_name", ""),
                fabrication_date=fdate,
                temperature=r.get("temperature", ""),
                db_path=db_path
            )
            imported_cnt += 1
        else:
            lr = local_map[k]
            if not lr.get("csv_data") and r.get("csv_data"):
                db_mod.update_record(
                    record_id=lr["id"],
                    sample_id=lr.get("sample_id"),
                    params=lr.get("params") or r.get("params", []),
                    notes=lr.get("notes") or r.get("notes", ""),
                    is_broken=int(lr.get("is_broken") or r.get("is_broken", 0)),
                    total_distance_mm=lr.get("total_distance_mm") or r.get("total_distance_mm"),
                    sem_photo_path=lr.get("sem_photo_path") or r.get("sem_photo_path"),
                    csv_path=lr.get("csv_path") or r.get("csv_path"),
                    csv_data=r.get("csv_data"),
                    initial_val=lr.get("initial_val") or r.get("initial_val"),
                    final_pct=lr.get("final_pct") or r.get("final_pct"),
                    min_pct=lr.get("min_pct") or r.get("min_pct"),
                    recipe_name=lr.get("recipe_name") or r.get("recipe_name"),
                    fabrication_date=lr.get("fabrication_date") or fdate,
                    temperature=lr.get("temperature") or r.get("temperature"),
                    db_path=db_path
                )
                updated_cnt += 1

    # クラウド側とも再同期（本番DBの場合のみ）
    if db_path == LOCAL_DB_PATH:
        try:
            sync_with_cloud(db_path=db_path)
        except Exception:
            pass

    return {
        "success": True,
        "imported_count": imported_cnt,
        "updated_count": updated_cnt,
        "total_records": len(db_mod.get_all_records(db_path=db_path))
    }
