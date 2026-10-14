import sqlite3
import json
import math
import os
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
from temperature_converter import convert_current_to_temperature

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "nanofiber_data.db")

def clean_for_json(obj: Any) -> Any:
    """NaN や Inf など JSON 準拠でない数値を安全に None または 0.0 に置換"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    return obj

def init_db(db_path: str = DB_PATH):
    """データベースとテーブルの初期化（マイグレーション対応）"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fabrication_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                photo_path TEXT,
                params_json TEXT NOT NULL,
                csv_path TEXT,
                csv_data_json TEXT,
                initial_val REAL,
                final_pct REAL,
                min_pct REAL,
                notes TEXT,
                sem_photo_path TEXT,
                total_distance_mm REAL,
                is_broken INTEGER DEFAULT 0
            )
        """)
        try:
            cursor.execute("ALTER TABLE fabrication_records ADD COLUMN sem_photo_path TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE fabrication_records ADD COLUMN total_distance_mm REAL")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE fabrication_records ADD COLUMN is_broken INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE fabrication_records ADD COLUMN recipe_name TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE fabrication_records ADD COLUMN fabrication_date TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE fabrication_records ADD COLUMN temperature TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE fabrication_records ADD COLUMN updated_at TEXT")
        except Exception:
            pass
        conn.commit()

def sync_with_cloud(custom_sync_dir: Optional[str] = None, db_path: str = DB_PATH) -> Dict[str, Any]:
    """クラウド / Google Drive 共有マスターとの双方向同期を実行"""
    try:
        import sync_manager
        return sync_manager.sync_with_cloud(db_path=db_path, custom_sync_dir=custom_sync_dir)
    except Exception as e:
        return {"success": False, "error": str(e), "total_records": len(get_all_records(db_path=db_path))}

def export_all_records_json(db_path: str = DB_PATH) -> str:
    """全レコードをJSONエクスポート"""
    import sync_manager
    return sync_manager.export_all_records_json(db_path=db_path)

def import_records_from_json(json_content_or_dict: Any, db_path: str = DB_PATH) -> Dict[str, Any]:
    """JSONからレコードを安全に取り込み・マージ"""
    import sync_manager
    return sync_manager.import_records_from_json(json_content_or_dict, db_path=db_path)

def resolve_media_file(filename_or_path: Optional[str]) -> Optional[str]:
    """メディア（SEM写真等）のローカル実パスを解決"""
    import sync_manager
    return sync_manager.resolve_media_file(filename_or_path)

def get_shared_sync_dir() -> str:
    """現在の同期ディレクトリを取得"""
    import sync_manager
    return sync_manager.get_shared_sync_dir()

def merge_databases(source_db_path: str, target_db_path: str = DB_PATH) -> Dict[str, Any]:
    """別のSQLiteデータベースファイルから全レコードを取り込み・マージ（古いスキーマの自動マイグレーションにも対応）"""
    if not os.path.exists(source_db_path):
        return {"success": False, "error": "指定されたファイルが存在しません"}
    try:
        init_db(source_db_path)
        source_records = get_all_records(include_csv_data=True, db_path=source_db_path)
        import sync_manager
        return sync_manager.import_records_from_json(source_records, db_path=target_db_path)
    except Exception as e:
        return {"success": False, "error": f"データベースマージ失敗: {str(e)}"}

def get_db_bytes(db_path: str = DB_PATH) -> bytes:
    """データベースファイル（nanofiber_data.db）をバイト列として取得"""
    init_db(db_path)
    with open(db_path, "rb") as f:
        return f.read()

def restore_db_from_bytes(data: bytes, db_path: str = DB_PATH) -> bool:
    """アップロードされたデータからデータベースを安全に復元・検証"""
    temp_path = db_path + ".temp"
    try:
        with open(temp_path, "wb") as f:
            f.write(data)
        with sqlite3.connect(temp_path) as test_conn:
            cursor = test_conn.cursor()
            cursor.execute("SELECT count(*) FROM fabrication_records")
            cursor.fetchone()
        if os.path.exists(db_path):
            os.replace(temp_path, db_path)
        else:
            os.rename(temp_path, db_path)
        return True
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False

def save_record(
    sample_id: str,
    params: List[Dict[str, Any]],
    photo_path: Optional[str] = None,
    csv_path: Optional[str] = None,
    csv_data: Optional[Dict[str, Any]] = None,
    initial_val: Optional[float] = None,
    final_pct: Optional[float] = None,
    min_pct: Optional[float] = None,
    notes: str = "",
    sem_photo_path: Optional[str] = None,
    total_distance_mm: Optional[float] = None,
    is_broken: int = 0,
    recipe_name: Optional[str] = "",
    fabrication_date: Optional[str] = "",
    temperature: Optional[str] = "",
    db_path: str = DB_PATH
) -> int:
    """作製レコードを保存"""
    init_db(db_path)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cleaned_params = clean_for_json(params)
    cleaned_csv_data = clean_for_json(csv_data) if csv_data else None

    params_json = json.dumps(cleaned_params, ensure_ascii=False)
    csv_data_json = json.dumps(cleaned_csv_data, ensure_ascii=False) if cleaned_csv_data else None

    safe_init_val = clean_for_json(initial_val)
    safe_final_pct = clean_for_json(final_pct)
    safe_min_pct = clean_for_json(min_pct)
    safe_dist = clean_for_json(total_distance_mm)
    safe_broken = int(is_broken) if is_broken else 0
    safe_recipe = str(recipe_name or "").strip()
    safe_date = str(fabrication_date or created_at.split(" ")[0]).strip()
    safe_temp = str(temperature or "").strip()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO fabrication_records (
                sample_id, created_at, photo_path, params_json, csv_path, csv_data_json,
                initial_val, final_pct, min_pct, notes, sem_photo_path, total_distance_mm, is_broken,
                recipe_name, fabrication_date, temperature, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sample_id, created_at, photo_path, params_json, csv_path, csv_data_json,
            safe_init_val, safe_final_pct, safe_min_pct, notes, sem_photo_path, safe_dist, safe_broken,
            safe_recipe, safe_date, safe_temp, created_at
        ))
        record_id = cursor.lastrowid
        conn.commit()

    # クラウド / Google Drive への自動同期（バックグラウンド反映）
    if db_path == DB_PATH:
        try:
            import sync_manager
            sync_manager.unregister_tombstone(sample_id, safe_date, created_at)
            sync_manager.sync_with_cloud(db_path=db_path)
        except Exception:
            pass

    return record_id

def get_all_records(include_csv_data: bool = False, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """すべての作製レコードを取得（最新順、include_csv_data=Falseで高速化）"""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fabrication_records ORDER BY id DESC")
        rows = cursor.fetchall()

    records = []
    for r in rows:
        row_dict = dict(r)
        try:
            p_data = json.loads(row_dict.get("params_json") or "[]")
        except Exception:
            p_data = []

        c_data = None
        if include_csv_data:
            try:
                c_data = json.loads(row_dict.get("csv_data_json") or "null")
            except Exception:
                c_data = None

        created_ts = row_dict.get("created_at") or ""
        fab_date = row_dict.get("fabrication_date") or (created_ts.split(" ")[0] if created_ts else "")
        records.append({
            "id": row_dict.get("id"),
            "sample_id": row_dict.get("sample_id"),
            "recipe_name": row_dict.get("recipe_name") or "",
            "fabrication_date": fab_date,
            "temperature": row_dict.get("temperature") or "",
            "created_at": created_ts,
            "photo_path": row_dict.get("photo_path"),
            "params": p_data,
            "csv_path": row_dict.get("csv_path"),
            "csv_data": c_data,
            "has_csv": bool(row_dict.get("csv_data_json")),
            "initial_val": row_dict.get("initial_val"),
            "final_pct": row_dict.get("final_pct"),
            "min_pct": row_dict.get("min_pct"),
            "notes": row_dict.get("notes") or "",
            "sem_photo_path": row_dict.get("sem_photo_path"),
            "total_distance_mm": row_dict.get("total_distance_mm"),
            "is_broken": int(row_dict.get("is_broken") or 0)
        })
    return records

def get_record_by_id(record_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """特定のレコードを取得"""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fabrication_records WHERE id = ?", (record_id,))
        row = cursor.fetchone()

    if not row:
        return None

    row_dict = dict(row)
    try:
        p_data = json.loads(row_dict.get("params_json") or "[]")
    except Exception:
        p_data = []
    try:
        c_data = json.loads(row_dict.get("csv_data_json") or "null")
    except Exception:
        c_data = None

    created_ts = row_dict.get("created_at") or ""
    fab_date = row_dict.get("fabrication_date") or (created_ts.split(" ")[0] if created_ts else "")
    return {
        "id": row_dict.get("id"),
        "sample_id": row_dict.get("sample_id"),
        "recipe_name": row_dict.get("recipe_name") or "",
        "fabrication_date": fab_date,
        "temperature": row_dict.get("temperature") or "",
        "created_at": created_ts,
        "photo_path": row_dict.get("photo_path"),
        "params": p_data,
        "csv_path": row_dict.get("csv_path"),
        "csv_data": c_data,
        "initial_val": row_dict.get("initial_val"),
        "final_pct": row_dict.get("final_pct"),
        "min_pct": row_dict.get("min_pct"),
        "notes": row_dict.get("notes") or "",
        "sem_photo_path": row_dict.get("sem_photo_path"),
        "total_distance_mm": row_dict.get("total_distance_mm"),
        "is_broken": int(row_dict.get("is_broken") or 0)
    }

def delete_record(record_id: int, db_path: str = DB_PATH) -> bool:
    """レコードを削除（クラウド同期マスターからも確実に消去）"""
    init_db(db_path)
    rec_info = get_record_by_id(record_id, db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fabrication_records WHERE id = ?", (record_id,))
        deleted = cursor.rowcount > 0
        conn.commit()

    if deleted and db_path == DB_PATH and rec_info:
        try:
            import sync_manager
            sync_manager.register_record_deletion(
                sample_id=rec_info.get("sample_id"),
                fab_date=rec_info.get("fabrication_date"),
                created_at=rec_info.get("created_at"),
                db_path=db_path
            )
        except Exception:
            pass
    return deleted

def update_sem_photo(record_id: int, sem_photo_path: str, db_path: str = DB_PATH) -> bool:
    """既存レコードのSEM写真パスを更新"""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE fabrication_records SET sem_photo_path = ? WHERE id = ?", (sem_photo_path, record_id))
        updated = cursor.rowcount > 0
        conn.commit()
    return updated

def update_broken_status(record_id: int, is_broken: int, db_path: str = DB_PATH) -> bool:
    """破断ステータスを更新"""
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE fabrication_records SET is_broken = ? WHERE id = ?", (int(is_broken), record_id))
        updated = cursor.rowcount > 0
        conn.commit()
    return updated

def update_record(
    record_id: int,
    sample_id: str,
    params: List[Dict[str, Any]],
    notes: str = "",
    is_broken: int = 0,
    total_distance_mm: Optional[float] = None,
    sem_photo_path: Optional[str] = None,
    csv_path: Optional[str] = None,
    csv_data: Optional[Dict[str, Any]] = None,
    initial_val: Optional[float] = None,
    final_pct: Optional[float] = None,
    min_pct: Optional[float] = None,
    recipe_name: Optional[str] = "",
    fabrication_date: Optional[str] = "",
    temperature: Optional[str] = "",
    db_path: str = DB_PATH
) -> bool:
    """既存レコードの全データを安全に更新（未変更のCSVや写真データを確実に保持）"""
    init_db(db_path)
    cleaned_params = clean_for_json(params)
    cleaned_csv_data = clean_for_json(csv_data) if csv_data else None

    params_json = json.dumps(cleaned_params, ensure_ascii=False)
    csv_data_json = json.dumps(cleaned_csv_data, ensure_ascii=False) if cleaned_csv_data else None

    safe_init_val = clean_for_json(initial_val)
    safe_final_pct = clean_for_json(final_pct)
    safe_min_pct = clean_for_json(min_pct)
    safe_dist = clean_for_json(total_distance_mm)
    safe_broken = int(is_broken) if is_broken else 0
    safe_recipe = str(recipe_name or "").strip()
    safe_date = str(fabrication_date or "").strip()
    safe_temp = str(temperature or "").strip()
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # CSVや写真が渡されていない場合、既存の保持データを誤って消去しないよう取得・保護
        if csv_data is None or sem_photo_path is None:
            cursor.execute("SELECT csv_path, csv_data_json, initial_val, final_pct, min_pct, sem_photo_path FROM fabrication_records WHERE id = ?", (record_id,))
            cur_row = cursor.fetchone()
            if cur_row:
                if csv_data is None and cur_row[1]:
                    csv_data_json = cur_row[1]
                    if csv_path is None or not csv_path:
                        csv_path = cur_row[0]
                    if safe_init_val is None:
                        safe_init_val = cur_row[2]
                    if safe_final_pct is None:
                        safe_final_pct = cur_row[3]
                    if safe_min_pct is None:
                        safe_min_pct = cur_row[4]
                if sem_photo_path is None and cur_row[5]:
                    sem_photo_path = cur_row[5]

        cursor.execute("""
            UPDATE fabrication_records SET
                sample_id = ?,
                params_json = ?,
                notes = ?,
                is_broken = ?,
                total_distance_mm = ?,
                sem_photo_path = ?,
                csv_path = ?,
                csv_data_json = ?,
                initial_val = ?,
                final_pct = ?,
                min_pct = ?,
                recipe_name = ?,
                fabrication_date = ?,
                temperature = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            sample_id, params_json, notes, safe_broken, safe_dist,
            sem_photo_path, csv_path, csv_data_json,
            safe_init_val, safe_final_pct, safe_min_pct, safe_recipe,
            safe_date, safe_temp, now_ts, record_id
        ))
        updated = cursor.rowcount > 0
        conn.commit()

    # クラウド / Google Drive への自動同期（バックグラウンド反映）
    if updated and db_path == DB_PATH:
        try:
            import sync_manager
            sync_manager.sync_with_cloud(db_path=db_path)
        except Exception:
            pass

    return updated

def safe_num(v, default=0.0):
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return default if math.isnan(v) or math.isinf(v) else float(v)
    try:
        val = float(v)
        return default if math.isnan(val) or math.isinf(val) else val
    except (ValueError, TypeError):
        return default

def get_record_metrics(rec: dict) -> dict:
    """作製データ履歴に必要な4大指標（温度、総加熱時間、延伸距離、延伸速度）を安全に算出"""
    if not rec:
        return {
            "temperature_str": "-",
            "total_time_s": 0.0,
            "total_time_str": "0s",
            "distance_mm": 0.0,
            "distance_str": "0.0mm",
            "speed_ums": 0.0,
            "speed_str": "0µm/s"
        }
    params = rec.get("params") or []
    # 1. 温度 (手動入力値があれば優先、未入力ならヒーター電流から自動換算)
    temp_val = str(rec.get("temperature") or "").strip()
    if not temp_val:
        currents = [safe_num(p.get("current_A")) for p in params if isinstance(p, dict) and safe_num(p.get("current_A")) > 0]
        if currents:
            conv_t = convert_current_to_temperature(currents[0])
            if conv_t is not None and conv_t > 0:
                temp_val = f"{conv_t:.0f}℃"
            else:
                temp_val = f"{currents[0]:.3f}A"
        else:
            temp_val = "-"
    elif not temp_val.endswith("℃") and not temp_val.endswith("°C") and temp_val.replace(".", "", 1).isdigit():
        temp_val = f"{temp_val}℃"

    # 2. 総加熱時間
    stop_times = [safe_num(p.get("stop_time_s"), 0.0) for p in params if isinstance(p, dict)]
    total_time = max(stop_times) if stop_times else 0.0

    # 3. 延伸距離
    dist_mm = rec.get("total_distance_mm")
    if dist_mm is None:
        tot_um = 0.0
        for p in params:
            if isinstance(p, dict):
                spd = safe_num(p.get("speed_ums"), 0.0)
                t_start = safe_num(p.get("start_time_s"), 0.0)
                t_stop = safe_num(p.get("stop_time_s"), 0.0)
                tot_um += spd * max(0.0, t_stop - t_start)
        dist_mm = tot_um / 1000.0
    else:
        dist_mm = safe_num(dist_mm, 0.0)

    # 4. 延伸速度
    speeds = [safe_num(p.get("speed_ums"), 0.0) for p in params if isinstance(p, dict)]
    max_spd = max(speeds) if speeds else 0.0

    return {
        "temperature_str": temp_val,
        "total_time_s": total_time,
        "total_time_str": f"{total_time:.0f}s",
        "distance_mm": round(dist_mm, 2),
        "distance_str": f"{dist_mm:.1f}mm",
        "speed_ums": max_spd,
        "speed_str": f"{max_spd:.0f}µm/s"
    }

def compute_param_signature(params: list) -> str:
    """作製ステップのパラメータ群から一意の条件シグネチャを生成（微小な誤差を吸収）"""
    if not params:
        return "empty"
    parts = []
    for idx, p in enumerate(params):
        if not isinstance(p, dict):
            continue
        c = round(safe_num(p.get("current_A"), 6.0), 2)
        s = round(safe_num(p.get("speed_ums"), 0.0), 0)
        t_start = safe_num(p.get("start_time_s"), 0.0)
        t_stop = safe_num(p.get("stop_time_s"), 0.0)
        dur = round(max(0.0, t_stop - t_start), 1)
        parts.append(f"{idx+1}:{c:.2f}A_{s:.0f}um_{dur:.0f}s")
    return "|".join(parts) if parts else "empty"

def get_condition_label(params: list, recipe_name: str = "") -> str:
    """条件の読みやすい表示名（レシピ名があればそれを優先、なければステップ要約）"""
    r_name = str(recipe_name or "").strip()
    if r_name:
        return r_name
    if not params:
        return "未設定条件"
    step_count = len(params)
    total_um = 0.0
    max_spd = 0.0
    for p in params:
        if isinstance(p, dict):
            spd = safe_num(p.get("speed_ums"), 0.0)
            max_spd = max(max_spd, spd)
            t_start = safe_num(p.get("start_time_s"), 0.0)
            t_stop = safe_num(p.get("stop_time_s"), 0.0)
            dur = max(0.0, t_stop - t_start)
            total_um += spd * dur
    total_mm = total_um / 1000.0
    return f"{step_count}段階延伸 (総延伸量: {total_mm:.2f} mm, 最大速度: {max_spd:.0f} µm/s)"

def matches_condition(rec: dict, target_params: list, target_recipe_name: str = "") -> bool:
    """レコードが指定された条件（レシピ名またはパラメータ群）と一致するか判定"""
    rec_recipe = str(rec.get("recipe_name") or "").strip()
    t_recipe = str(target_recipe_name or "").strip()
    
    # 1. どちらも条件名が設定されている場合、条件名の一致を優先
    if rec_recipe and t_recipe:
        return rec_recipe.lower() == t_recipe.lower()
        
    # 2. 条件名のどちらかが空の場合、パラメータシグネチャで一致判定
    sig_rec = compute_param_signature(rec.get("params", []))
    sig_target = compute_param_signature(target_params)
    if sig_rec != "empty" and sig_target != "empty" and sig_rec == sig_target:
        return True
        
    # 3. 指定条件名とレコードの条件名が一致する場合
    if t_recipe and rec_recipe and t_recipe.lower() == rec_recipe.lower():
        return True
        
    return False

def calculate_yield_stats(matching_records: list) -> dict:
    """一致した作製レコード群から歩留まり統計を算出"""
    total = len(matching_records)
    if total == 0:
        return {
            "total_count": 0,
            "intact_count": 0,
            "broken_count": 0,
            "yield_rate": 0.0,
            "avg_final_pct": None,
            "std_final_pct": 0.0,
            "min_final_pct": None,
            "max_final_pct": None,
            "high_yield_rate_80": 0.0,
            "avg_loss_db": None,
            "samples": []
        }

    intact_records = [r for r in matching_records if not r.get("is_broken")]
    broken_records = [r for r in matching_records if r.get("is_broken")]
    intact_cnt = len(intact_records)
    broken_cnt = len(broken_records)
    yield_rate = (intact_cnt / total) * 100.0

    finals = [r["final_pct"] for r in intact_records if r.get("final_pct") is not None]
    if finals:
        avg_f = float(np.mean(finals))
        std_f = float(np.std(finals)) if len(finals) > 1 else 0.0
        min_f = float(np.min(finals))
        max_f = float(np.max(finals))
        high_80 = len([f for f in finals if f >= 80.0])
        high_yield_80 = (high_80 / total) * 100.0

        losses = [-10.0 * np.log10(max(f / 100.0, 1e-6)) for f in finals if f > 0]
        avg_loss = float(np.mean(losses)) if losses else None
    else:
        avg_f, std_f, min_f, max_f = None, 0.0, None, None
        high_yield_80 = 0.0
        avg_loss = None

    sample_summaries = []
    for r in matching_records:
        f_pct = r.get("final_pct")
        loss = None
        if f_pct is not None and f_pct > 0:
            loss = -10.0 * np.log10(max(f_pct / 100.0, 1e-6))
        sample_summaries.append({
            "id": r["id"],
            "sample_id": r.get("sample_id"),
            "recipe_name": r.get("recipe_name") or "",
            "created_at": r.get("created_at"),
            "is_broken": int(r.get("is_broken", 0)),
            "final_pct": f_pct,
            "loss_db": loss,
            "total_distance_mm": r.get("total_distance_mm"),
            "notes": r.get("notes", "")
        })

    return {
        "total_count": total,
        "intact_count": intact_cnt,
        "broken_count": broken_cnt,
        "yield_rate": yield_rate,
        "avg_final_pct": avg_f,
        "std_final_pct": std_f,
        "min_final_pct": min_f,
        "max_final_pct": max_f,
        "high_yield_rate_80": high_yield_80,
        "avg_loss_db": avg_loss,
        "samples": sample_summaries
    }

def get_condition_yield_stats(all_records: list, target_params: list, target_recipe_name: str = "") -> dict:
    """指定条件に合致するレコードを抽出し、歩留まり統計を返す"""
    matched = [r for r in all_records if matches_condition(r, target_params, target_recipe_name)]
    return calculate_yield_stats(matched)

def get_all_conditions_yield_summary(all_records: list) -> list:
    """全レコードを同一作製条件ごとにグループ化し、条件別歩留まり集計リストを返す"""
    groups = {}
    for r in all_records:
        r_name = str(r.get("recipe_name") or "").strip()
        params = r.get("params", [])
        sig = compute_param_signature(params)
        # グループキー: レシピ名があればレシピ名、なければパラメータシグネチャ
        group_key = f"NAME:{r_name.lower()}" if r_name else f"SIG:{sig}"
        if group_key not in groups:
            groups[group_key] = {
                "recipe_name": r_name,
                "params": params,
                "label": get_condition_label(params, r_name),
                "records": []
            }
        groups[group_key]["records"].append(r)

    summary_list = []
    for g_key, g_data in groups.items():
        stats = calculate_yield_stats(g_data["records"])
        step_cnt = len(g_data["params"]) if g_data["params"] else 0
        total_mm = None
        valid_dists = [r["total_distance_mm"] for r in g_data["records"] if r.get("total_distance_mm") is not None]
        if valid_dists:
            total_mm = float(np.mean(valid_dists))
        summary_list.append({
            "group_key": g_key,
            "condition_name": g_data["label"],
            "recipe_name": g_data["recipe_name"],
            "step_count": step_cnt,
            "avg_dist_mm": total_mm,
            "total_count": stats["total_count"],
            "intact_count": stats["intact_count"],
            "broken_count": stats["broken_count"],
            "yield_rate": stats["yield_rate"],
            "avg_final_pct": stats["avg_final_pct"],
            "std_final_pct": stats["std_final_pct"],
            "avg_loss_db": stats["avg_loss_db"],
            "high_yield_rate_80": stats["high_yield_rate_80"],
            "samples": stats["samples"]
        })

    # 作製数が多い順、歩留まりが高い順にソート
    summary_list.sort(key=lambda x: (x["total_count"], x["yield_rate"]), reverse=True)
    return summary_list



